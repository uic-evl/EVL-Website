# _plugins/redirects.rb

require "fileutils"
require "json"

Jekyll::Hooks.register :site, :post_write do |site|
  redirects = site.data["redirects"] || []

  redirects.each do |redirect|
    to = redirect["to"]
    next unless to

    Array(redirect["from"]).each do |from|
      next unless from

      path = from.sub(%r{^/}, "")
      path = "#{path}index.html" if from.end_with?("/")

      output = File.join(site.dest, path)

      FileUtils.mkdir_p(File.dirname(output))

      File.write(output, <<~HTML)
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <meta http-equiv="refresh" content="0; url=#{to}">
          <link rel="canonical" href="#{to}">
          <script>
            window.location.replace(#{to.to_json});
          </script>
          <title>Redirecting...</title>
        </head>
        <body>
          <p>Redirecting to <a href="#{to}">#{to}</a>...</p>
        </body>
        </html>
      HTML

      puts "Redirect: #{from} -> #{to}"
    end
  end
end
