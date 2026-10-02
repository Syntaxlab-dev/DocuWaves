---
order: 3
published: true
title: Accessibility
---

What the reading site does for people who are not using it the usual way.
This is a description of the behaviour, not a conformance claim — see
[Scope and limitations](/p/docuwaves/pages/scope-and-limitations).

## Keyboard and screen readers

- **A skip link** is the first thing in the tab order on every page: one
  press of Tab, one press of Enter, and the focus is on the article rather
  than at the top of the navigation for the twentieth time.
- **Landmarks.** The header, the navigation, the article and the footer are
  the elements they say they are, so a screen reader's own jump-to-region
  works.
- **The theme button says which way it goes** — "switch to the dark view" —
  rather than being an unlabelled moon.
- **The contents list marks where you are** with `aria-current`, not only
  with a colour, so the position is announced and not merely seen.
- **Headings are a real outline.** Page titles are `h1`, `##` and `###`
  become `h2`/`h3`, and nothing is a heading because it looked big.

## Motion

The application has very little animation, and what there is respects
`prefers-reduced-motion`. A reader whose system asks for less motion gets
it, without a setting on this site to find.

## Colour and contrast

Both themes are built for readable contrast on body text, and the accent
colour is a link colour rather than the only thing distinguishing one state
from another. If you set your own [accent
colour](/p/docuwaves/pages/branding-this-instance), that is the one thing
here you can make worse — check it against the background in both themes.

## Images and media

Alt text is yours to write, and it is the one part of accessibility this
application cannot do for you. It matters most on
[video and audio](/p/docuwaves/pages/formulas-video-and-audio), where a
reader who cannot play the file has nothing but that sentence.

## What is not claimed

No audit has been done, no conformance level is claimed, and nobody has
tested this against a standard. The list above is what the code does; it is
not an assessment, and it is not a statement about WCAG or any other
framework. If you need one, it has to be made by somebody qualified to make
it, about your instance.
