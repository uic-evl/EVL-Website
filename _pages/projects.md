---
layout: page
title: Projects
permalink: /projects/
description: Projects developed at EVL.
nav: true
nav_order: 4
display_statuses: [active, past]
horizontal: false
---

<!-- pages/projects.md -->
<div class="projects">
{% comment %}
  Projects are grouped by the `status` field in their front matter (active or past).
  A project without a status is shown under active.
{% endcomment %}
{% for status in page.display_statuses %}
  {% if status == "past" %}
    {% assign status_projects = site.projects | where: "status", "past" %}
  {% else %}
    {% assign status_projects = site.projects | where_exp: "p", "p.status != 'past'" %}
  {% endif %}
  {% assign sorted_projects = status_projects | sort: "importance" %}

  {% if sorted_projects.size > 0 %}
  <a id="{{ status }}" href=".#{{ status }}">
    <h2 class="category">{{ status }}</h2>
  </a>

  <!-- Generate cards for each project -->
  {% if page.horizontal %}
  <div class="container">
    <div class="row row-cols-1 row-cols-md-2">
    {% for project in sorted_projects %}
      {% include projects_horizontal.liquid %}
    {% endfor %}
    </div>
  </div>
  {% else %}
  <div class="row row-cols-1 row-cols-md-3">
    {% for project in sorted_projects %}
      {% include projects.liquid %}
    {% endfor %}
  </div>
  {% endif %}
  {% endif %}
{% endfor %}
</div>
