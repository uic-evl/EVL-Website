
# frozen_string_literal: true

module LocalRedirects

  class RedirectPage < Jekyll::Page
    include Jekyll::Filters::URLFilters

    DEFAULT_DATA = {
      "sitemap" => false,
      "layout"  => "redirect"
    }.freeze

    def self.from_paths(site, from, to)
      page = new(site, site.source, "", "redirect.html")
      page.set_paths(from, to)
      page
    end

    def read_yaml(_base, _name, _opts = {})
      self.content = self.output = ""
      self.data ||= DEFAULT_DATA.dup
    end


    def set_paths(from, to)
      self.data ||= DEFAULT_DATA.dup
    
      from = "/#{from}" unless from.start_with?("/")
    
      data.merge!(
        "permalink" => from,
        "redirect" => {
          "from" => from,
          "to"   => to.to_s
        }
      )
    end

    def redirect_from
      data["redirect"]["from"] if data["redirect"]
    end

    def redirect_to
      data["redirect"]["to"] if data["redirect"]
    end
  end


  class Generator < Jekyll::Generator
    safe true

    def generate(site)
      redirects = site.data["redirects"] || []

      redirects.each do |entry|
        to = entry["to"]

        Array(entry["from"]).each do |from|
          page = RedirectPage.from_paths(site, from, to)
          site.pages << page

          Jekyll.logger.info "Redirect:", "#{from} -> #{to}"
        end
      end
    end
  end

end

