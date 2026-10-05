---
layout: default
---

{% for post in site.posts limit:20 %}
<article>
  <h2><a href="{{ post.url | relative_url }}">{{ post.title | escape }}</a></h2>
  <p><small>{{ post.date | date: "%-d %B %Y" }}</small></p>
  {{ post.content }}
</article>
<hr>
{% endfor %}
