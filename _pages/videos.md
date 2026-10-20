---
layout: page
title: Videos
permalink: /videos/
description: Videos from EVL's YouTube channel, evltube.
nav: true
nav_order: 8
_styles: >
  .yt-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 1.25rem; margin: 0 0 2.5rem; }
  .yt-card { display: none; }
  .yt-card.yt-show { display: block; }
  .yt-player { position: relative; aspect-ratio: 16 / 9; background: #000; border-radius: .5rem; overflow: hidden; cursor: pointer; }
  .yt-player img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .yt-player iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; }
  .yt-play { position: absolute; left: 50%; top: 50%; width: 64px; height: 44px; margin: -22px 0 0 -32px; background: rgba(0,0,0,.65); border-radius: 12px; }
  .yt-play::after { content: ""; position: absolute; left: 26px; top: 12px; border-style: solid; border-width: 10px 0 10px 18px; border-color: transparent transparent transparent #fff; }
  .yt-player:hover .yt-play { background: var(--global-theme-color); }
  .yt-title { margin: .6rem 0 .15rem; font-weight: 600; line-height: 1.3; }
  .yt-meta { color: var(--global-text-color-light); font-size: .85rem; }
  .yt-head { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; flex-wrap: wrap; }
  .yt-head h2 { margin-bottom: .25rem; }
  .yt-head a, .yt-head button { font-size: .9rem; }
  .yt-head button { background: none; border: 1px solid var(--global-divider-color); border-radius: .4rem; padding: .2rem .7rem; color: inherit; cursor: pointer; }
---

{% assign yt = site.data.youtube %}
{% if yt and yt.videos.size > 0 %}

<p>EVL has published {{ yt.count }} videos on its YouTube channel, <a href="{{ yt.channel.url }}" target="_blank" rel="noopener">evltube</a>, since 2007, with {{ yt.views | divided_by: 1000 }}K views in total. Below, a random pick of recent videos and the most watched ones. Counts were collected on {{ yt.collected }}.</p>

<div class="yt-head">
  <h2 id="newest">Recent videos</h2>
  <button type="button" id="yt-shuffle" hidden>Show another pick</button>
</div>
<div class="yt-grid" id="yt-newest">
{%- assign newest = yt.videos | sort: "published" | reverse | slice: 0, 24 %}
{%- for v in newest %}
  <div class="yt-card{% if forloop.index <= 6 %} yt-show{% endif %}" data-id="{{ v.id }}">
    <div class="yt-player" data-id="{{ v.id }}" title="Play {{ v.title | escape }}">
      <img src="https://i.ytimg.com/vi/{{ v.id }}/hqdefault.jpg" alt="{{ v.title | escape }}" loading="lazy">
      <span class="yt-play"></span>
    </div>
    <div class="yt-title">{{ v.title }}</div>
    <div class="yt-meta">{{ v.published | date: "%B %-d, %Y" }} · {{ v.views }} views</div>
  </div>
{%- endfor %}
</div>

<div class="yt-head">
  <h2 id="most-viewed">Most viewed</h2>
  <a href="{{ yt.channel.url }}/videos?view=0&sort=p" target="_blank" rel="noopener">All videos by popularity on YouTube</a>
</div>
<div class="yt-grid">
{%- assign top = yt.videos | sort: "views" | reverse | slice: 0, 6 %}
{%- for v in top %}
  <div class="yt-card yt-show">
    <div class="yt-player" data-id="{{ v.id }}" title="Play {{ v.title | escape }}">
      <img src="https://i.ytimg.com/vi/{{ v.id }}/hqdefault.jpg" alt="{{ v.title | escape }}" loading="lazy">
      <span class="yt-play"></span>
    </div>
    <div class="yt-title">{{ v.title }}</div>
    <div class="yt-meta">{{ v.published | date: "%B %-d, %Y" }} · {{ v.views }} views</div>
  </div>
{%- endfor %}
</div>

<script>
(function () {
  // A different random pick of recent videos on every visit; without JavaScript the six newest show.
  var grid = document.getElementById("yt-newest");
  var cards = Array.prototype.slice.call(grid.querySelectorAll(".yt-card"));
  function shuffle() {
    var order = cards.slice();
    for (var i = order.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = order[i]; order[i] = order[j]; order[j] = t;
    }
    cards.forEach(function (c) { c.classList.remove("yt-show"); });
    order.slice(0, 6).forEach(function (c) { c.classList.add("yt-show"); grid.appendChild(c); });
  }
  var button = document.getElementById("yt-shuffle");
  if (cards.length > 6) {
    button.hidden = false;
    button.addEventListener("click", shuffle);
    shuffle();
  }

  // Thumbnails become the player only when clicked, so the page does not load a dozen YouTube players.
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
