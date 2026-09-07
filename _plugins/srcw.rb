
Jekyll::Hooks.register [:documents, :pages], :post_render do |doc|
  next unless doc.output_ext == ".html"

  doc.output = doc.output.gsub(/(<img\b[^>]*?\bsrc=")([^"]+)(")/i) do
    pre, src, post = $1, $2, $3
    if src =~ /-srcw\.jpg$/i
      "#{pre}#{src}#{post}"
    elsif src =~ %r{^/images/.+\.(jpe?g|png|tiff?|webp|bmp|heic|avif)$}i
      "#{pre}#{src}-srcw.jpg#{post}"
    else
      "#{pre}#{src}#{post}"
    end
  end
end
