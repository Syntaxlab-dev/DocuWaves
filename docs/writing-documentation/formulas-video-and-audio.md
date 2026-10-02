---
order: 8
published: true
title: Formulas, video and audio
---

Two things a page can hold besides text, images and
[diagrams](/p/docuwaves/pages/diagrams).

## Mathematical notation

LaTeX, rendered by KaTeX. Inline between single dollars, display between
double:

```markdown
The complexity is $O(n \log n)$ for the sorted case.

$$
\sigma = \sqrt{\frac{1}{N}\sum_{i=1}^{N}(x_i - \mu)^2}
$$
```

A single `$` in ordinary prose — a price, a shell variable — is left alone;
it takes a matching pair on the same line to be read as maths.

Nothing extra is loaded for this. KaTeX is already in the bundle, so a page
with a formula on it costs no additional request, and an instance with no
internet access renders one exactly the same.

## Video and audio

The image syntax takes media files too:

```markdown
![Recording of the import running end to end](../assets/import-run.mp4)
```

A video renders with the browser's own controls; an audio file renders as an
audio player. The alt text is used as the accessible label, and it earns its
place here more than on an image — a reader who cannot play the file has
only that sentence.

Upload them the same way as images: the **Insert image** button, or drag
them onto the editor. See [Images](/p/docuwaves/pages/images).

**Accepted:** `.mp4`, `.webm`, `.ogg` for video; `.mp3`, `.m4a`, `.wav` for
audio.

**Only an image can be a cover.** A project's or category's tile picture has
to be a picture, so the two lists are kept separate: everything here is
servable, but `image:` in a `_project.yml` or `_category.yml` takes an image
file.

### The 10 MB limit applies, and is not raised for video

Every file in a page goes into your **content repository**, and Git stores
every version of every binary forever. A clone of that repository — which is
what a contributor does, and what a restore does — pulls all of them down.
Three 40 MB screen recordings, revised twice each, is a repository that is
slow to clone for as long as it exists.

For anything longer than a short clip, host it where video is hosted and
link to it. A documentation page that embeds a 90-second demo is doing
something different from one that is a video player.
