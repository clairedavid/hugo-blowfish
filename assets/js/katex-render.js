/* Override of themes/blowfish/assets/js/katex-render.js.

   The theme's own auto-render call passes no delimiter config, so KaTeX
   falls back to its built-in default list: $$...$$, \(...\), \[...\] and a
   few \begin{...} environments. Plain $...$ is not in that list. This site's
   research content writes its maths as $r_s$, $10^{-3}$ etc. (matching
   config/_default/markup.toml's own goldmark passthrough, which likewise
   only names $$...$$ and \(...\), never bare $...$), so without this file
   every such expression would render as literal, un-rendered text, with no
   console error to flag it: confirmed by testing the theme's unmodified
   default against this exact maths before adding this override.

   The fix is one added entry in the delimiters list. Everything else here is
   the theme's file verbatim. */
document.getElementById("katex-render") &&
  document.getElementById("katex-render").addEventListener("load", () => {
    renderMathInElement(document.body, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "\\[", right: "\\]", display: true },
        { left: "\\(", right: "\\)", display: false },
        { left: "$", right: "$", display: false }
      ]
    });
  });
