---
order: 5
published: true
title: Writing help in the editor
---

With the [documentation chat's model](/p/docuwaves/pages/the-documentation-chat)
configured, the Markdown editor offers **AI writing help**. Select some
text, open the writing help above the editor and choose:

- **Rephrase**: the same facts, more clearly worded
- **Shorten**: about half as long, without dropping what a reader needs
- **Say it simpler**: plain language for someone new to the topic
- **Fix spelling**: spelling, grammar and punctuation only
- **Summarise**: two to four sentences, or a short list

The suggestion appears below the buttons. **Use it** replaces the selection
with it; nothing is stored until the page is saved, and undo works as
usual. If the selected text has changed in the meantime, the suggestion is
not used, so nothing typed in between gets lost.

## What the model is told

The same rule as for the chat and for drafts from search gaps: work only
with the selected text, and add no facts. No command, setting, version or
number comes from the model's general knowledge. Links keep their targets,
code stays as it is, and lists, headings and callouts keep their markers.
A model can still get this wrong, so read the suggestion before using it.

## Who can use it and what is sent

Everyone who may edit the page. Only the selected text goes to the model,
at most 8,000 characters at a time, to the same endpoint as the chat. A
model you run yourself (Ollama, for example) keeps it on your own server.
In the visual editor, switch to Markdown to use it.
