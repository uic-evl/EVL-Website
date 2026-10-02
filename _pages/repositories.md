---
layout: page
permalink: /repositories/
title: Repositories
description:
nav: false
---

{% if site.data.repositories.github_users %}

## GitHub Users

<div class="repositories d-flex flex-wrap flex-md-row flex-column justify-content-between align-items-center">
  {% for user in site.data.repositories.github_users %}
    {% include repository/repo_user.liquid username=user %}
  {% endfor %}
</div>

{% endif %}

{% if site.data.repositories.github_organizations %}

## GitHub Organizations

<div class="repositories">
  {% for org in site.data.repositories.github_organizations %}
    <div class="organization-info" style="text-align: left; margin-bottom: 20px;">
      <h4 id="{{ org }}-display-name">Fetching organization name...</h4>
      <p id="{{ org }}-description">Fetching stats for {{ org }}...</p>

      <!-- This will be populated with stats dynamically -->
      <ul id="{{ org }}-stats">
        <li><strong>Public Repositories:</strong> Loading...</li>
        <li><strong>Followers:</strong> Loading...</li>
        <li><strong>Location:</strong> Loading...</li>
      </ul>

      <!-- This will be populated with repositories dynamically -->
      <h5>Repositories:</h5>
      <ul id="{{ org }}-repos">
        <li>Loading repositories...</li>
      </ul>

      <p>Visit our GitHub organization at <a href="https://github.com/{{ org }}" target="_blank">https://github.com/{{ org }}</a>.</p>
    </div>

    <hr>
  {% endfor %}
</div>

<script>
  document.addEventListener('DOMContentLoaded', function() {
    const organizations = {{ site.data.repositories.github_organizations | jsonify }};
    const onlyRepos = {{ site.data.repositories.github_organization_repos | jsonify }} || {};

    // GitHub allows 60 unauthenticated API requests per hour, so the page makes two per organization
    // (its info and its repository list) and nothing per repository.
    function fetchJson(url) {
      return fetch(url).then(response => {
        if (!response.ok) throw new Error(`GitHub API answered ${response.status} for ${url}`);
        return response.json();
      });
    }

    organizations.forEach(org => {
      // Fetch organization info and stats
      fetchJson(`https://api.github.com/orgs/${org}`)
        .then(data => {
          // Update the organization display name
          document.getElementById(`${org}-display-name`).textContent = data.name || org;

          // Update the organization stats on the page
          document.getElementById(`${org}-description`).textContent = data.description || "No description available.";
          document.getElementById(`${org}-stats`).innerHTML = `
            <li><strong>Public Repositories:</strong> ${data.public_repos}</li>
            <li><strong>Followers:</strong> ${data.followers}</li>
            <li><strong>Location:</strong> ${data.location || "No location available"}</li>
          `;

          // Fetch organization repositories with pagination
          fetchAllRepos(data.repos_url, org, 1, []);
        })
        .catch(error => {
          console.error('Error fetching organization data:', error);
          document.getElementById(`${org}-display-name`).textContent = org;
          document.getElementById(`${org}-description`).textContent = "Error fetching data";
          document.getElementById(`${org}-repos`).innerHTML = "<li>Error fetching repositories.</li>";
        });
    });

    // Function to recursively fetch repositories from paginated API, then sort and display them
    function fetchAllRepos(reposUrl, org, page, allRepos) {
      fetchJson(`${reposUrl}?per_page=100&page=${page}`)
        .then(repos => {
          // Append the current page of repositories to the allRepos array
          allRepos = allRepos.concat(repos);

          // If there are exactly 100 repos, fetch the next page
          if (repos.length === 100) {
            fetchAllRepos(reposUrl, org, page + 1, allRepos);
            return;
          }

          // Keep only the listed repositories of an organization that has a list
          const only = onlyRepos[org];
          const shown = only ? allRepos.filter(repo => only.includes(repo.name)) : allRepos;
          if (shown.length === 0) {
            // If there are no repositories at all
            document.getElementById(`${org}-repos`).innerHTML = "<li>No repositories available.</li>";
          } else {
            sortAndDisplay(shown, org);
          }
        })
        .catch(error => {
          console.error('Error fetching repositories:', error);
          document.getElementById(`${org}-repos`).innerHTML = "<li>Error fetching repositories.</li>";
        });
    }

    // The date of a repository's last push, which the repository list already carries
    function lastPush(repo) {
      return new Date(repo.pushed_at || repo.updated_at);
    }

    // Function to sort repos by last push (most recent first) and display them
    function sortAndDisplay(repos, org) {
      const reposElement = document.getElementById(`${org}-repos`);
      repos.sort((a, b) => lastPush(b) - lastPush(a));

      reposElement.innerHTML = '';
      repos.forEach(repo => {
        const li = document.createElement('li');
        li.id = repo.name;
        li.innerHTML = `
          <a href="${repo.html_url}" target="_blank">${repo.name}</a>:
          ${repo.description || "No description available."}
          (Last updated: ${lastPush(repo).toLocaleDateString()})
        `;
        reposElement.appendChild(li);
      });
    }

  });
</script>

{% endif %}

{% if site.data.repositories.github_repos %}

## GitHub Repositories

<div class="repositories d-flex flex-wrap flex-md-row flex-column justify-content-between align-items-center">
  {% for repo in site.data.repositories.github_repos %}
    {% include repository/repo.liquid repository=repo %}
  {% endfor %}
</div>

{% endif %}
