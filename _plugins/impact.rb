# Builds the Impact page (/impact/): its model in site.data["impact_model"], and /impact/impact.json and
# /impact/evl-impact.csv with the same numbers.
#
# Counted from this site's files at every build:
#   publications and citations   the bibliography the Publications page renders; authors from _data/people.csv
#   PhD graduates                _data/people.csv (the Members page)
#   funded projects and funding  _data/grants.csv (the Funding page)
# Read from _data/impact_metrics.json, which _impact/collect.mjs writes and the impact workflow commits:
#   repositories, stars, downloads, and the citations of each bibliography entry
#
# A problem in any source is logged and leaves its row "Not available"; it never stops the build.

require "bibtex"
require "cgi"
require "csv"
require "date"
require "json"

module EvlImpact
  URL = "https://www.evl.uic.edu/impact/"
  CODE = "https://github.com/uic-evl/EVL-Website/blob/deployment"
  MEMBER_STATUSES = %w[faculty emeritus].freeze
  NOT_PUBLICATIONS = %w[misc unpublished].freeze
  NOT_TITLE_SEARCHED = %w[misc unpublished phdthesis mastersthesis].freeze
  GROUPS = [
    ["Research", %w[publications citations phd-graduates]],
    ["Funding", %w[funded-projects new-funding]],
    ["Open source", %w[repositories stars downloads]],
  ].freeze

  # Lowercase ASCII words: HTML entities, LaTeX accents, commands and braces, and diacritics removed.
  def self.words(text)
    s = CGI.unescapeHTML(text.to_s)
    s = s.gsub(/\\[a-zA-Z]+\s*/, "").gsub(/\\./, "").delete("{}")
    s.unicode_normalize(:nfd).gsub(/\p{Mn}/, "").downcase.gsub(/[^a-z0-9]+/, " ").strip
  end

  # Text for display: LaTeX accents decoded, braces removed.
  def self.display(text)
    s = text.to_s
    begin
      require "latex/decode"
      s = LaTeX.decode(s)
    rescue LoadError, StandardError
      s = s.gsub(/\\[a-zA-Z]+\s*/, "").gsub(/\\./, "")
    end
    s.delete("{}").gsub(/\s+/, " ").strip
  end

  def self.number(value)
    value.to_i.to_s.reverse.scan(/\d{1,3}/).join(",").reverse
  end

  def self.dollars(value)
    "$#{number(value)}"
  end

  def self.long_date(date)
    date.strftime("%B %-d, %Y")
  end

  class Model
    attr_reader :years, :rows, :updated

    def initialize(site)
      @site = site
      @config = site.data["impact"] || {}
      @metrics = site.data["impact_metrics"]
      @today = Date.today
      start = Integer(@config["start"] || 2020) rescue 2020
      @years = (start..@today.year).to_a
      @updated = (Date.iso8601(@metrics["collected"].to_s) rescue nil) if @metrics
      @rows = {}
    end

    def build
      safely("publications") { publications_and_citations }
      safely("phd-graduates") { phd_graduates }
      safely("funded-projects") { funding }
      safely("repositories") { repositories }
      safely("stars") { stars }
      safely("downloads") { downloads }
      self
    end

    def warn(message)
      Jekyll.logger.warn("Impact:", message)
    end

    # A row whose source failed reads "Not available" everywhere.
    def safely(id)
      yield
    rescue StandardError => e
      warn("#{id} could not be counted: #{e.class}: #{e.message}")
      ids = id == "publications" ? %w[publications citations] : id == "funded-projects" ? %w[funded-projects new-funding] : [id]
      ids.each { |i| @rows[i] = row(i, LABELS[i], @years.map { nil }, rule: "This row could not be counted when the site was last built.") }
    end

    LABELS = {
      "publications" => "Publications",
      "citations" => "Citations",
      "phd-graduates" => "PhD graduates",
      "funded-projects" => "Funded projects (active)",
      "new-funding" => "New funding (UIC share)",
      "repositories" => "Open repositories (total)",
      "stars" => "GitHub stars (total)",
      "downloads" => "Package downloads",
    }.freeze

    def row(id, label, values, money: false, rule: nil, sources: [], items: [])
      text = values.map { |v| v.nil? ? "Not available" : money ? EvlImpact.dollars(v) : EvlImpact.number(v) }
      { "id" => id, "label" => label, "values" => values, "text" => text, "rule" => rule, "sources" => sources, "items" => items }
    end

    def in_years(year)
      @years.include?(year)
    end

    # people.csv rows with a member status, as last name and first initial.
    def members
      (@site.data["people"] || []).each_with_object({}) do |p, keys|
        next unless MEMBER_STATUSES.include?(p["status"].to_s.strip)
        last = EvlImpact.words(p["dirLastName"])
        first = EvlImpact.words(p["dirFirstName"])
        if last.empty? || first.empty?
          warn("people.csv row #{p['name'].inspect} has no dirLastName or dirFirstName; it is not matched")
          next
        end
        keys["#{last}|#{first[0]}"] = p["name"]
      end
    end

    def bib_entries
      scholar = @site.config["scholar"] || {}
      file = File.join(@site.source, scholar["source"].to_s.sub(%r{^/+}, ""), scholar["bibliography"].to_s)
      BibTeX.open(file).data.grep(BibTeX::Entry)
    end

    def authors(entry)
      value = entry[:author]
      names = value.is_a?(BibTeX::Names) ? value : (BibTeX::Names.parse(value.to_s) || [])
      names.map do |n|
        last = EvlImpact.words([n.prefix, n.last].compact.join(" "))
        last = EvlImpact.words(n.last) if last.empty?
        "#{last}|#{EvlImpact.words(n.first)[0]}"
      end
    rescue StandardError
      []
    end

    def publications_and_citations
      keys = members
      counted = Hash.new(0)
      cited_keys = []
      entries = bib_entries
      entries.each do |entry|
        type = entry.type.to_s.downcase
        next if NOT_PUBLICATIONS.include?(type)
        next unless authors(entry).any? { |a| keys.key?(a) }
        cited_keys << entry.key.to_s
        year = entry[:year].to_s[/\d{4}/].to_i
        counted[year] += 1 if in_years(year)
      end
      @rows["publications"] = row(
        "publications", LABELS["publications"], @years.map { |y| counted[y] },
        rule: "Entries of the <a href=\"/publications/\">Publications</a> page, by year, that have at least one author " \
              "who is EVL faculty or emeritus faculty on the <a href=\"/people/\">Members</a> page. Authors are matched by " \
              "last name and first initial. Preprints and other <code>@misc</code> and <code>@unpublished</code> entries are " \
              "not counted. A PhD or MS thesis counts here when an EVL faculty member is among its authors; PhD graduates " \
              "have their own row.",
        sources: [{ "label" => "Publications", "url" => "/publications/" }, { "label" => "Members", "url" => "/people/" }],
      )
      citations(cited_keys, entries)
    end

    def citations(cited_keys, entries)
      lookups = @metrics&.dig("citations", "lookups")
      works = @metrics&.dig("citations", "works")
      unless lookups && works
        @rows["citations"] = row("citations", LABELS["citations"], @years.map { nil }, rule: citations_rule)
        return
      end
      types = entries.to_h { |e| [e.key.to_s, e.type.to_s.downcase] }
      ids = cited_keys.filter_map { |k| lookups.dig(k, "id") }.uniq
      values = @years.map { |y| ids.sum { |id| works.dig(id, y.to_s).to_i } }
      found = cited_keys.count { |k| lookups.dig(k, "id") }
      missing = cited_keys.count { |k| lookups.key?(k) && !lookups.dig(k, "id") }
      pending = cited_keys.count { |k| !lookups.key?(k) && !NOT_TITLE_SEARCHED.include?(types[k]) }
      unsearched = cited_keys.count { |k| !lookups.key?(k) && NOT_TITLE_SEARCHED.include?(types[k]) }
      coverage = "Of the #{EvlImpact.number(cited_keys.size)} entries counted, of any year, " \
                 "#{EvlImpact.number(found)} are in OpenAlex and #{EvlImpact.number(missing)} were not found"
      coverage += "; #{EvlImpact.number(pending)} titles are still to be looked up" if pending.positive?
      coverage += "; #{EvlImpact.number(unsearched)} theses without a DOI or arXiv id are not looked up" if unsearched.positive?
      @rows["citations"] = row(
        "citations", LABELS["citations"], values, rule: citations_rule,
        sources: [{ "label" => "OpenAlex", "url" => "https://openalex.org/" }],
        items: [{ "heading" => "Coverage", "entries" => ["#{coverage}."] }],
      )
    end

    def citations_rule
      "Citations received in each year by the entries the Publications row counts, whatever year they were " \
        "published, from OpenAlex. An entry is found in OpenAlex by its DOI, then its arXiv id, then its exact title. " \
        "Two entries for the same work count once."
    end

    # "PhD 21", "PhD 2021" or "MS 14, PhD 21" in the alumni column; two-digit years up to this year are 20xx.
    def phd_year(value)
      m = value.to_s.match(/\bPhD\s*'?(\d{4}|\d{2})\b/i) or return nil
      y = m[1].to_i
      return y if m[1].size == 4
      y <= @today.year % 100 ? 2000 + y : 1900 + y
    end

    def phd_graduates
      by_year = Hash.new { |h, k| h[k] = [] }
      (@site.data["people"] || []).each do |p|
        y = phd_year(p["alumni"])
        by_year[y] << CGI.unescapeHTML(p["name"].to_s.strip) if y && in_years(y)
      end
      items = @years.reverse.filter_map do |y|
        next if by_year[y].empty?
        { "heading" => y.to_s, "entries" => by_year[y].sort.map { |n| CGI.escapeHTML(n) } }
      end
      @rows["phd-graduates"] = row(
        "phd-graduates", LABELS["phd-graduates"], @years.map { |y| by_year[y].size },
        rule: "People on the <a href=\"/people/\">Members</a> page whose degrees include a PhD in that year.",
        sources: [{ "label" => "Members", "url" => "/people/" }],
        items: items,
      )
    end

    def grants
      (@site.data["grants"] || []).each_with_index.filter_map do |g, i|
        title = CGI.unescapeHTML((g["ShortTitle"].to_s.strip.empty? ? g["LongTitle"] : g["ShortTitle"]).to_s.strip)
        where = "grants.csv row #{i + 2} (#{title.empty? ? g['Code'] : title})"
        begin
          start = Date.iso8601(g["StartDate"].to_s.strip)
          finish = Date.iso8601(g["EndDate"].to_s.strip)
        rescue ArgumentError, TypeError
          warn("#{where} has no valid StartDate or EndDate; it is not counted")
          next
        end
        amount = g["UICAward"].to_s.gsub(/[$,\s]/, "")
        unless amount.match?(/\A\d+(\.\d+)?\z/)
          warn("#{where} has no valid UICAward; it is not counted")
          next
        end
        funder = g["Funder"].to_s.strip
        { "title" => title, "funder" => funder.empty? ? "Other" : funder, "start" => start, "end" => finish,
          "amount" => amount.to_f.round, "link" => g["Link"].to_s.strip }
      end
    end

    def funding
      list = grants
      active = ->(g, y) { g["start"] <= Date.new(y, 12, 31) && g["end"] >= Date.new(y, 1, 1) }
      started = ->(g, y) { g["start"].year == y }
      shown = list.select { |g| g["end"] >= Date.new(@years.first, 1, 1) }.sort_by { |g| [g["start"], g["title"]] }
      entries = shown.map do |g|
        name = g["link"].empty? ? CGI.escapeHTML(g["title"]) : "<a href=\"#{CGI.escapeHTML(g['link'])}\">#{CGI.escapeHTML(g['title'])}</a>"
        "#{name}, #{CGI.escapeHTML(g['funder'])}, #{g['start'].strftime('%b %Y')} to #{g['end'].strftime('%b %Y')}, #{EvlImpact.dollars(g['amount'])}"
      end
      sources = [{ "label" => "Funding", "url" => "/about/funding/" }]
      @rows["funded-projects"] = row(
        "funded-projects", LABELS["funded-projects"], @years.map { |y| list.count { |g| active.(g, y) } },
        rule: "Grants in this site's grant list (<code>_data/grants.csv</code>, the list the <a href=\"/about/funding/\">Funding</a> " \
              "page shows) that were active at any time in the year. The Funding page shows current grants only; this row " \
              "also counts grants that have ended.",
        sources: sources, items: [{ "heading" => "Grants active since #{@years.first}", "entries" => entries }],
      )
      @rows["new-funding"] = row(
        "new-funding", LABELS["new-funding"], @years.map { |y| list.select { |g| started.(g, y) }.sum { |g| g["amount"] } },
        money: true,
        rule: "The UIC share of the grants that started in the year, as the Funding page lists it.",
        sources: sources,
      )
    end

    def orgs
      Array((@site.data["repositories"] || {})["github_organizations"])
    end

    def metric_repos
      Array(@metrics&.fetch("repos", nil))
    end

    def repositories
      repos = metric_repos
      return @rows["repositories"] = row("repositories", LABELS["repositories"], @years.map { nil }, rule: repositories_rule) unless @metrics
      exists = ->(r, y) { r["created"].to_s[0, 4].to_i <= y }
      entries = orgs.map do |org|
        mine = repos.select { |r| r["org"] == org }
        forks = mine.count { |r| r["fork"] }
        "<a href=\"https://github.com/#{org}\">#{org}</a>: #{mine.size} repositories#{forks.positive? ? ", #{forks} of them forks" : ''}"
      end
      @rows["repositories"] = row(
        "repositories", LABELS["repositories"], @years.map { |y| repos.count { |r| exists.(r, y) } },
        rule: repositories_rule, sources: [{ "label" => "Repositories", "url" => "/repositories/" }],
        items: [{ "heading" => "Today", "entries" => entries }],
      )
    end

    def repositories_rule
      "The public repositories the <a href=\"/repositories/\">Repositories</a> page lists, forks included, that " \
        "existed at the end of each year. Only repositories that are public today are counted."
    end

    # A repository's stars at the end of a year, or nil when they are not known for that year.
    def repo_stars(repo, y, snapshots)
      if repo["starred"]
        repo["starred"].sum { |year, n| year.to_i <= y ? n.to_i : 0 }
      elsif (snap = snapshots[repo["repo"]])
        first = (Date.iso8601(snap["first"].to_s) rescue nil)
        return nil unless first && y >= first.year
        snap.dig("years", y.to_s)
      end
    end

    def stars
      return @rows["stars"] = row("stars", LABELS["stars"], @years.map { nil }, rule: stars_rule) unless @metrics
      repos = metric_repos
      snapshots = @metrics["starSnapshots"] || {}
      by_org = orgs.to_h do |org|
        mine = repos.select { |r| r["org"] == org }
        [org, @years.map do |y|
          counts = mine.map { |r| r["created"].to_s[0, 4].to_i > y ? 0 : repo_stars(r, y, snapshots) }
          counts.include?(nil) ? nil : counts.sum
        end]
      end
      values = @years.each_index.map do |i|
        known = by_org.values.map { |v| v[i] }.compact
        known.empty? ? nil : known.sum
      end
      firsts = snapshots.values.filter_map { |s| Date.iso8601(s["first"].to_s) rescue nil }
      late = by_org.select { |_, v| v.include?(nil) }.keys
      since = late.any? && firsts.any? ? " The stars of #{late.join(' and ')} are counted from #{EvlImpact.long_date(firsts.min)} on." : ""
      @rows["stars"] = row(
        "stars", LABELS["stars"], values, rule: stars_rule + since,
        sources: [{ "label" => "Repositories", "url" => "/repositories/" }],
      )
    end

    def stars_rule
      "All the stars of the repositories the Open repositories row counts, at the end of each year. A star counts " \
        "from the day it was given; stars that were taken back are not counted."
    end

    def downloads
      return @rows["downloads"] = row("downloads", LABELS["downloads"], @years.map { nil }, rule: downloads_rule) unless @metrics
      packages = []
      { "pypi" => "PyPI", "npm" => "npm" }.each do |source, registry|
        (@metrics.dig(source, "packages") || {}).sort.each do |name, pkg|
          url = source == "pypi" ? "https://pypi.org/project/#{name}/" : "https://www.npmjs.com/package/#{name}"
          packages << { "label" => "#{name} (#{registry})", "url" => url, "repo" => pkg["repo"],
                        "values" => @years.map { |y| pkg.dig("years", y.to_s).to_i } }
        end
      end
      values = @years.each_index.map { |i| packages.sum { |p| p["values"][i] } }
      entries = packages.map { |p| "<a href=\"#{p['url']}\">#{CGI.escapeHTML(p['label'])}</a>, from <a href=\"https://github.com/#{p['repo']}\">#{p['repo']}</a>" }
      @rows["downloads"] = row(
        "downloads", LABELS["downloads"], values, rule: downloads_rule,
        sources: [{ "label" => "ClickHouse PyPI dataset", "url" => "https://clickhouse.com/docs/getting-started/example-datasets/pypi" },
                  { "label" => "npm download counts", "url" => "https://github.com/npm/registry/blob/main/docs/download-counts.md" }],
        items: [{ "heading" => "Packages", "entries" => entries }],
      )
    end

    def downloads_rule
      "Downloads in each year of the packages that the listed repositories publish, under their current names " \
        "(<code>_data/impact.yml</code>). PyPI downloads come from ClickHouse's public PyPI dataset and include " \
        "mirrors; npm downloads come from npm's download counts. Installing a package also downloads the packages it " \
        "depends on, so one install of <code>@urban-toolkit/autk</code> counts once for each autk package."
    end

    def ordered
      n = 0
      GROUPS.map do |label, ids|
        { "label" => label, "rows" => ids.filter_map { |id| @rows[id]&.merge("n" => (n += 1), "group" => label) } }
      end
    end

    def to_liquid_hash
      current = @years.last
      {
        "years" => @years.map { |y| { "label" => y.to_s, "current" => y == current } },
        "updated" => @updated && EvlImpact.long_date(@updated),
        "through" => EvlImpact.long_date(@updated || @today),
        "groups" => ordered,
      }
    end

    def to_json_hash
      {
        "updated" => @updated&.iso8601,
        "url" => URL,
        "years" => @years.map { |y| { "label" => y.to_s, "current" => y == @years.last } },
        "rows" => ordered.flat_map do |g|
          g["rows"].map do |r|
            { "id" => r["id"], "group" => g["label"], "label" => r["label"], "values" => r["values"] }
          end
        end,
      }
    end

    def to_csv
      CSV.generate do |csv|
        csv << ["EVL impact", URL]
        csv << ["Collected numbers last updated", @updated&.iso8601 || "Not available"]
        csv << ["Category", "Metric", *@years.map { |y| y == @years.last ? "#{y} (so far)" : y.to_s }]
        ordered.each do |g|
          g["rows"].each { |r| csv << [g["label"], r["label"], *r["values"]] }
        end
      end
    end
  end

  class ImpactFile < Jekyll::PageWithoutAFile
    def initialize(site, name, content)
      super(site, site.source, "impact", name)
      self.content = content
      data["layout"] = nil
      data["sitemap"] = false
      data["render_with_liquid"] = false
    end
  end

  class Generator < Jekyll::Generator
    safe true
    priority :normal

    def generate(site)
      model = Model.new(site).build
      site.data["impact_model"] = model.to_liquid_hash
      site.pages << ImpactFile.new(site, "impact.json", JSON.pretty_generate(model.to_json_hash))
      site.pages << ImpactFile.new(site, "evl-impact.csv", model.to_csv)
    rescue StandardError => e
      Jekyll.logger.warn("Impact:", "the page could not be built: #{e.class}: #{e.message}")
      site.data["impact_model"] = nil
    end
  end
end
