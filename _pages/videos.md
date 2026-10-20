---
layout: page
title: Videos
permalink: /videos/
description: Videos from EVL's YouTube channel, evltube.
nav: true
nav_order: 8
_styles: >
  .yt-stats { display: flex; flex-wrap: wrap; gap: 2.5rem; margin: .5rem 0 2.5rem; }
  .yt-stats div { display: flex; flex-direction: column; }
  .yt-stats b { font-size: 1.9rem; font-weight: 700; line-height: 1.1; color: var(--global-theme-color); font-variant-numeric: tabular-nums; }
  .yt-stats span { font-size: .85rem; color: var(--global-text-color-light); text-transform: uppercase; letter-spacing: .06em; margin-top: .25rem; }
  .yt-head { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem; padding-bottom: .5rem; border-bottom: 1px solid var(--global-divider-color); }
  .yt-head h2 { margin: 0; font-size: 1.5rem; }
  .yt-head a { font-size: .85rem; }
  .yt-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1.5rem 1.25rem; margin: 0 0 3rem; }
  .yt-player { position: relative; aspect-ratio: 16 / 9; background: #000; border-radius: .6rem; overflow: hidden; cursor: pointer; box-shadow: 0 1px 3px rgba(0,0,0,.12); transition: transform .2s, box-shadow .2s; }
  .yt-card:hover .yt-player { transform: translateY(-3px); box-shadow: 0 8px 20px rgba(0,0,0,.18); }
  .yt-player img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .yt-player iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }
  .yt-play { position: absolute; left: 50%; top: 50%; width: 58px; height: 40px; margin: -20px 0 0 -29px; background: rgba(0,0,0,.6); border-radius: 10px; transition: background .15s; }
  .yt-play::after { content: ""; position: absolute; left: 23px; top: 11px; border-style: solid; border-width: 9px 0 9px 16px; border-color: transparent transparent transparent #fff; }
  .yt-card:hover .yt-play { background: var(--global-theme-color); }
  .yt-length { position: absolute; right: .5rem; bottom: .5rem; padding: .1rem .4rem; border-radius: .3rem; background: rgba(0,0,0,.75); color: #fff; font-size: .75rem; font-variant-numeric: tabular-nums; }
  .yt-title { margin: .7rem 0 .2rem; font-weight: 600; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .yt-meta { color: var(--global-text-color-light); font-size: .85rem; }
  .yt-rank { display: inline-block; min-width: 1.6rem; margin-right: .35rem; color: var(--global-theme-color); font-weight: 700; }
---

{% assign yt = site.data.youtube %}
{% if yt and yt.videos.size > 0 %}

<p>EVL has been publishing on YouTube since 2007: lectures, demos, and the making of the lab's displays, from the CAVE to the Arcade. The latest uploads, and the ones most people have watched. Counts collected on {{ yt.collected }}.</p>

<div class="yt-stats">
  <div><b>{{ yt.count }}</b><span>videos</span></div>
  <div><b>{{ yt.views | divided_by: 100000.0 | round | divided_by: 10.0 }}M</b><span>views</span></div>
  <div><b>{{ yt.videos.last.published | date: "%Y" }}</b><span>first upload</span></div>
  <div><b><a href="{{ yt.channel.url }}" target="_blank" rel="noopener">evltube</a></b><span>on YouTube</span></div>
</div>

<div class="yt-head">
  <h2 id="latest">Latest</h2>
  <a href="{{ yt.channel.url }}/videos" target="_blank" rel="noopener">All videos by date</a>
</div>
<div class="yt-grid" id="yt-latest">
{%- assign newest = yt.videos | sort: "published" | reverse | slice: 0, 9 %}
{%- for v in newest %}
  <div class="yt-card">
    <div class="yt-player" data-id="{{ v.id }}" title="Play: {{ v.title | escape }}">
      <img src="https://i.ytimg.com/vi/{{ v.id }}/hqdefault.jpg" alt="{{ v.title | escape }}" loading="lazy">
      <span class="yt-play"></span>
      {%- if v.seconds > 0 %}<span class="yt-length">{{ v.seconds | divided_by: 60 }}:{{ v.seconds | modulo: 60 | prepend: "00" | slice: -2, 2 }}</span>{% endif %}
    </div>
    <div class="yt-title">{{ v.title }}</div>
    <div class="yt-meta">{{ v.published | date: "%B %-d, %Y" }} · {% if v.views >= 1000 %}{{ v.views | divided_by: 1000.0 | round }}K{% else %}{{ v.views }}{% endif %} views</div>
  </div>
{%- endfor %}
</div>

<div class="yt-head">
  <h2 id="most-viewed">Most viewed</h2>
  <a href="{{ yt.channel.url }}/videos?view=0&sort=p" target="_blank" rel="noopener">All videos by popularity</a>
</div>
<div class="yt-grid">
{%- assign top = yt.videos | sort: "views" | reverse | slice: 0, 9 %}
{%- for v in top %}
  <div class="yt-card">
    <div class="yt-player" data-id="{{ v.id }}" title="Play: {{ v.title | escape }}">
      <img src="https://i.ytimg.com/vi/{{ v.id }}/hqdefault.jpg" alt="{{ v.title | escape }}" loading="lazy">
      <span class="yt-play"></span>
      {%- if v.seconds > 0 %}<span class="yt-length">{{ v.seconds | divided_by: 60 }}:{{ v.seconds | modulo: 60 | prepend: "00" | slice: -2, 2 }}</span>{% endif %}
    </div>
    <div class="yt-title"><span class="yt-rank">{{ forloop.index }}</span>{{ v.title }}</div>
    <div class="yt-meta">{{ v.published | date: "%B %-d, %Y" }} · {% if v.views >= 1000000 %}{{ v.views | divided_by: 100000.0 | round | divided_by: 10.0 }}M{% elsif v.views >= 1000 %}{{ v.views | divided_by: 1000.0 | round }}K{% else %}{{ v.views }}{% endif %} views</div>
  </div>
{%- endfor %}
</div>

<script>
(function () {
  // Thumbnails become the player only when clicked, so the page does not load fifteen YouTube players.
  document.addEventListener("click", function (e) {
    var player = e.target.closest(".yt-player");
    if (!player || player.querySelector("iframe")) return;
    var iframe = document.createElement("iframe");
    iframe.src = "https://www.youtube-nocookie.com/embed/" + player.dataset.id + "?autoplay=1&rel=0";
    iframe.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
    iframe.allowFullscreen = true;
    iframe.title = player.title;
    player.innerHTML = "";
    player.appendChild(iframe);
  });
})();
</script>

{% else %}

<p>The video list has not been collected yet. Meanwhile, visit <a href="https://www.youtube.com/user/evltube" target="_blank" rel="noopener">evltube on YouTube</a>.</p>

{% endif %}
