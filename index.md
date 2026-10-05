---
layout: default
---

<p>This page automatically mirrors the last 5 posts from the Whiteshill and Ruscombe Community Facebook page. Posts appear here shortly after they are published on Facebook.</p>

<p><strong>Want an email when there's a new post?</strong>
Go to <a href="https://blogtrottr.com">blogtrottr.com</a>, paste in this feed address, <code>{{ '/feed.xml' | absolute_url }}</code>, add your email address and choose how often you'd like updates. It's free, and you can unsubscribe at any time.</p>
<hr>

{% for post in site.posts limit:40 %}
<article>
  <h2><a href="{{ post.url | relative_url }}">{{ post.title | escape }}</a></h2>
  <p><small>{{ post.date | date: "%-d %B %Y" }}</small></p>
  {{ post.content }}
</article>
<hr>
{% endfor %}
