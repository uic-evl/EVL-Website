---
layout: page
title: The Urban Toolkit
description: A suite of tools for urban visual analytics
img: assets/img/urbantk/urbantk.png
importance: 1
category: research
status: active
tags: [urban, visual analytics, open-source]
_styles: >
  .utk-impact td, .utk-impact thead th { text-align: right; }
  .utk-impact thead th:first-child { text-align: left; }
  .utk-impact small { display: block; font-weight: normal; color: var(--global-text-color-light); }
# The toolkit's projects, in urbantk.org's order. Each card shows the project's image from urbantk.org
# (assets/img/urbantk/<slug>.webp) and links to https://urbantk.org/<slug>/.
toolkit:
  - heading: Grammars & toolkits
    projects:
      - { slug: utk, name: UTK, tagline: Grammar for urban visualizations, alt: What-if shadow analysis and building-level sunlight access specified with the UTK grammar }
      - { slug: streetweave, name: StreetWeave, tagline: Grammar for street-overlaid visualizations, alt: Eight street network visualizations made with StreetWeave }
      - { slug: autark, name: Autark, tagline: "Load, process, and visualize geospatial data entirely in the browser", alt: Urbane rebuilt with Autark }
  - heading: Dataflow frameworks
    projects:
      - { slug: curio, name: Curio, tagline: Dataflow-based framework for collaboration in urban visual analytics, alt: "Dataflows built in Curio for urban accessibility, climate and sunlight access studies" }
      - { slug: urbanite, name: Urbanite, tagline: Dataflow-based framework for Human-AI alignment in urban visual analytics, alt: Analyzing flood simulations with Urbanite }
  - heading: Knowledge bases & guidelines
    projects:
      - { slug: va-blueprint, name: VA-Blueprint, tagline: LLM-generated knowledge base for visual analytics system components, alt: From visual analytics papers to a hierarchical blueprint of system components }
      - { slug: survey-3d, name: Survey 3D, tagline: Survey on 3D urban visual analytics, alt: The structure of the survey }
  - heading: AI & ML
    projects:
      - { slug: shadows, name: Deep Umbra, tagline: Generative approach for city-scale shadow computation, alt: "A single timestep shadow next to shadows accumulated over a time range, over a 3D city" }
      - { slug: tile2net, name: tile2net, tagline: Automatic generation of sidewalk networks from aerial imagery, alt: "Overview of tile2net, from aerial imagery to a sidewalk network" }
      - { slug: citysurfaces, name: CitySurfaces, tagline: Segmentation of sidewalk surfaces from street-level images, alt: "Sidewalk paving materials mapped in Chicago, Washington DC and Brooklyn" }
      - { slug: neural-3d, name: neural-3d, tagline: Neural fields for view computation and data exploration in 3D cities, alt: Direct and inverse view queries over building facades }
---

<div class="row justify-content-sm-center">
  <div class="col-sm-8 col-md-6 mt-3 mt-md-0">
    {% include figure.liquid path="assets/img/urbantk/urbantk-wheel.png" alt="The Urban Toolkit's projects around its logo, grouped into grammars and toolkits, dataflow frameworks, knowledge bases, and AI and ML" class="img-fluid" sizes="(min-width: 768px) 400px, 95vw" %}
  </div>
</div>

The Urban Toolkit is a growing ecosystem of open-source tools, frameworks, knowledge bases, and methods designed to simplify and accelerate urban data visualization and analysis. It enables researchers, experts, and developers to explore complex urban phenomena through high-level visual grammars, map-centric interactions, and curated datasets.

Links:
- Main project site: [urbantk.org](https://urbantk.org)
- Code: [github.com/urban-toolkit](https://github.com/urban-toolkit)
- Papers: [urbantk.org/papers](https://urbantk.org/papers/)

## OSCUR

The development of the Urban Toolkit is supported by the Open-Source Cyberinfrastructure for Urban Computing Research ([OSCUR](https://oscur.org/)), the National Science Foundation project "Collaborative Research: Frameworks: Cyberinfrastructure to Catalyze and Sustain the Urban Computing Community" (NSF awards 2411221, 2411222 and 2411223). OSCUR is a $5 million collaboration between UIC, New York University and the University of Washington, with $1.75 million allocated to UIC. At UIC it is led by EVL faculty member Fabio Miranda (PI) and Sybil Derrible (co-PI) of Civil, Materials, and Environmental Engineering, and includes the departments of Computer Science and Civil, Materials, and Environmental Engineering and the College of Urban Planning and Public Affairs. The grant runs from September 2024 to August 2029.

OSCUR addresses two obstacles in urban computing: the lack of documented, robust, well-engineered tools and open computing platforms, and a dispersed community of cross-disciplinary researchers and developers. At its core is a cyberinfrastructure of scalable, reusable and interoperable methods and tools for urban data, covering data discovery, cleaning, analytics, modeling, visualization, and reproducibility.

More on OSCUR: [oscur.org](https://oscur.org/), [UIC Researchers Join National Project to Turn Urban Data into Healthier Cities](/news/2024/2024-09-01-2838/), and [OSCUR](/news/2024/2024-09-01-2846/).

## Impact

Two of the numbers urbantk.org collects each time it is published. Each year runs from September to August.

<div id="utk-impact" hidden>
  <table class="table table-sm utk-impact">
    <thead>
      <tr id="utk-impact-years"><th scope="col">Metric</th></tr>
    </thead>
    <tbody id="utk-impact-rows"></tbody>
  </table>
</div>
<p><span id="utk-impact-updated"></span>How each number is counted: <a href="https://urbantk.org/impact/">urbantk.org/impact</a>.</p>

## Projects

{% for group in page.toolkit %}
<h3>{{ group.heading }}</h3>
<div class="projects">
  <div class="row row-cols-1 row-cols-md-3">
    {% for p in group.projects %}
    {% assign img = "assets/img/urbantk/" | append: p.slug | append: ".webp" %}
    <div class="col">
      <a href="https://urbantk.org/{{ p.slug }}/">
        <div class="card h-100 hoverable">
          {% include figure.liquid loading="lazy" path=img sizes="(min-width: 768px) 320px, 95vw" alt=p.alt class="card-img-top" %}
          <div class="card-body">
            <h4 class="card-title">{{ p.name }}</h4>
            <p class="card-text">{{ p.tagline }}</p>
          </div>
        </div>
      </a>
    </div>
    {% endfor %}
  </div>
</div>
{% endfor %}

Images and numbers: [urbantk.org](https://urbantk.org).

<script>
  document.addEventListener('DOMContentLoaded', function() {
    // The rows of urbantk.org/impact/ shown above. urbantk.org recomputes them every time it is published,
    // and its build fails if either row goes missing from impact.json.
    const rowIds = ['downloads-month', 'publications'];

    fetch('https://urbantk.org/impact/impact.json')
      .then(response => {
        if (!response.ok) throw new Error(`urbantk.org answered ${response.status}`);
        return response.json();
      })
      .then(impact => {
        const rows = rowIds.map(id => impact.rows.find(row => row.id === id));
        if (rows.some(row => !row)) throw new Error('impact.json has no ' + rowIds.join(' or ') + ' row');

        const years = document.getElementById('utk-impact-years');
        impact.years.forEach(year => {
          const th = document.createElement('th');
          th.scope = 'col';
          th.textContent = year.label;
          const period = document.createElement('small');
          period.textContent = year.period;
          th.appendChild(period);
          years.appendChild(th);
        });

        const body = document.getElementById('utk-impact-rows');
        rows.forEach(row => {
          const tr = document.createElement('tr');
          const label = document.createElement('th');
          label.scope = 'row';
          label.textContent = row.label;
          tr.appendChild(label);
          row.values.forEach(value => {
            const td = document.createElement('td');
            td.textContent = value === null ? 'Not available' : value.toLocaleString('en-US');
            tr.appendChild(td);
          });
          body.appendChild(tr);
        });

        document.getElementById('utk-impact-updated').textContent = `Last updated ${impact.updated}. `;
        document.getElementById('utk-impact').hidden = false;
      })
      .catch(error => console.error('Error fetching the Urban Toolkit impact numbers:', error));
  });
</script>
