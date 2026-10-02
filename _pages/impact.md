---
layout: page
title: Impact
permalink: /impact/
description: EVL's research, funding and open-source work, year by year.
nav: true
nav_order: 5
_styles: >
  .evl-impact { font-variant-numeric: tabular-nums; }
  .evl-impact td, .evl-impact thead th { text-align: right; white-space: nowrap; }
  .evl-impact thead th:first-child, .evl-impact tbody th { text-align: left; }
  .evl-impact thead small { display: block; font-weight: normal; color: var(--global-text-color-light); }
  .evl-impact .evl-impact-group th { padding-top: 1rem; font-weight: 600; color: var(--global-theme-color); }
  .evl-impact-ref { margin-left: .2em; font-size: .75em; font-weight: normal; vertical-align: super; }
  .evl-impact-counted > li { margin-bottom: .75rem; }
  .evl-impact-counted .evl-impact-list { margin-top: .25rem; }
---

{% assign impact = site.data.impact_model %}
{% if impact %}

<p>EVL's publications, citations, PhD graduates, funding and open-source work by calendar year since {{ impact.years.first.label }}. The numbers come from this site's <a href="/publications/">Publications</a>, <a href="/people/">Members</a>, <a href="/about/funding/">Funding</a> and <a href="/repositories/">Repositories</a> pages, and change when those pages do.</p>

<p>{% if impact.updated %}Citations, repositories and downloads were last collected on {{ impact.updated }}.{% else %}Citations, repositories and downloads have not been collected yet.{% endif %} Download the table as <a href="/impact/evl-impact.csv" download>CSV</a> or <a href="/impact/impact.json">JSON</a>.</p>

<div class="table-responsive">
<table class="table table-sm evl-impact">
<thead>
<tr>
<th scope="col">Metric</th>
{%- for y in impact.years %}
<th scope="col">{{ y.label }}{% if y.current %}<small>so far</small>{% endif %}</th>
{%- endfor %}
</tr>
</thead>
{%- for group in impact.groups %}
<tbody>
<tr class="evl-impact-group"><th scope="rowgroup" colspan="{{ impact.years.size | plus: 1 }}">{{ group.label }}</th></tr>
{%- for row in group.rows %}
<tr>
<th scope="row">{{ row.label }}<a class="evl-impact-ref" href="#counted-{{ row.id }}">[{{ row.n }}]</a></th>
{%- for v in row.text %}
<td>{{ v }}</td>
{%- endfor %}
</tr>
{%- endfor %}
</tbody>
{%- endfor %}
</table>
</div>

## What is counted

<ol class="evl-impact-counted">
{%- for group in impact.groups %}
{%- for row in group.rows %}
<li id="counted-{{ row.id }}"><strong>{{ row.label }}.</strong> {{ row.rule }}
{%- if row.sources.size > 0 %} Sources: {% for s in row.sources %}<a href="{{ s.url }}">{{ s.label }}</a>{% unless forloop.last %}, {% endunless %}{% endfor %}.{% endif %}
{%- for item in row.items %}
<div class="evl-impact-list">{{ item.heading }}:<ul>{% for e in item.entries %}<li>{{ e }}</li>{% endfor %}</ul></div>
{%- endfor %}
</li>
{%- endfor %}
{%- endfor %}
</ol>

## Notes

<ul>
<li>Years are calendar years. {{ impact.years.last.label }} runs through {{ impact.through }}.</li>
<li>Code: <a href="https://github.com/uic-evl/EVL-Website/blob/deployment/_plugins/impact.rb">_plugins/impact.rb</a> counts every row when the site is built, and <a href="https://github.com/uic-evl/EVL-Website/blob/deployment/_impact/collect.mjs">_impact/collect.mjs</a> collects citations, repositories and downloads once a week and whenever the bibliography or the repository list changes.</li>
</ul>

{% else %}

<p>The impact numbers could not be computed for this version of the site.</p>

{% endif %}
