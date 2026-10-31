# Keeps _data/people.csv the one list of people: warns at build time about any name in another data file that
# doesn't match a row's "name" exactly. Checked:
#   people.csv  advisor  (full names, ";" between them)
#   grants.csv  PI, CoI  (CoI names separated by ",")
#   courses.csv Name
# People outside EVL who appear in those files go in OUTSIDE_EVL. A warning never stops the build.

module EvlPeopleNames
  OUTSIDE_EVL = [
    "Tom Gao",               # Pharmaceutical Sciences, co-advisor
    "Ameen Salahudeen",      # NIH grant co-investigators
    "Hananeh Esmailbeigi",
    "Xinhua Zhang",
  ].freeze

  def self.check(site)
    people = site.data["people"] || []
    known = people.map { |p| p["name"].to_s.strip }.to_set + OUTSIDE_EVL
    unknown = Hash.new { |h, k| h[k] = [] }

    people.each do |p|
      p["advisor"].to_s.split(";").map(&:strip).reject(&:empty?).each { |n| unknown[n] << "people.csv advisor of #{p['name']}" }
    end
    (site.data["grants"] || []).each do |g|
      ([g["PI"]] + g["CoI"].to_s.split(",")).compact.map(&:strip).reject(&:empty?).each do |n|
        unknown[n] << "grants.csv #{g['Code'].to_s.empty? ? g['ShortTitle'] : g['Code']}"
      end
    end
    (site.data["courses"] || []).each do |c|
      n = c["Name"].to_s.strip
      unknown[n] << "courses.csv #{c['Course'].to_s.strip}" unless n.empty?
    end

    unknown.reject { |n, _| known.include?(n) }.each do |n, where|
      Jekyll.logger.warn "People:", "\"#{n}\" is not a name in _data/people.csv (#{where.uniq.first(3).join('; ')})"
    end
  end
end

Jekyll::Hooks.register :site, :post_read do |site|
  EvlPeopleNames.check(site)
end
