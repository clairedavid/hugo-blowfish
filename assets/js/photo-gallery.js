/* About page photo gallery ("In Pictures").
   Reads the photo list from #pgal-data (serialised by the shortcode from
   data/photo_gallery.json), then wires the thumbnail grid to a lightbox.
   Close: the X button, a click outside the image, or Esc.
   Move: left and right arrow keys, or the on-screen arrows.
   No dependencies, nothing fetched at runtime. */
(function () {
  "use strict";

  var root = document.getElementById("pgal");
  var dataEl = document.getElementById("pgal-data");
  if (!root || !dataEl) return;

  var photos;
  try {
    photos = JSON.parse(dataEl.textContent);
  } catch (e) {
    return;
  }
  if (!photos || !photos.length) return;

  var lb = root.querySelector(".gal-lb");
  var lbSrc = root.querySelector(".gal-lb-src");
  var lbImg = root.querySelector(".gal-lb-img");
  var lbCap = root.querySelector(".gal-lb-cap");
  var btnX = root.querySelector(".gal-lb-x");
  var btnPrev = root.querySelector(".gal-lb-prev");
  var btnNext = root.querySelector(".gal-lb-next");
  if (!lb || !lbImg) return;

  var current = -1;
  var lastFocus = null;

  function show(i) {
    var p = photos[((i % photos.length) + photos.length) % photos.length];
    current = ((i % photos.length) + photos.length) % photos.length;
    // Setting width and height from the master's real pixel dimensions lets
    // the browser reserve the right box before the file arrives, so the
    // lightbox does not jump, and it keeps each photo's own aspect ratio.
    lbImg.width = p.w;
    lbImg.height = p.h;
    lbSrc.srcset = p.webp;
    lbImg.src = p.jpg;
    lbImg.alt = p.caption;
    lbCap.textContent = p.caption;
  }

  function open(i) {
    lastFocus = document.activeElement;
    show(i);
    lb.hidden = false;
    // The page must not scroll behind the overlay.
    document.documentElement.style.overflow = "hidden";
    btnX.focus();
  }

  function close() {
    lb.hidden = true;
    document.documentElement.style.overflow = "";
    lbImg.removeAttribute("src");
    lbSrc.removeAttribute("srcset");
    if (lastFocus && lastFocus.focus) lastFocus.focus();
    current = -1;
  }

  root.querySelectorAll(".gal-shot").forEach(function (btn) {
    btn.addEventListener("click", function () {
      open(parseInt(btn.getAttribute("data-i"), 10) || 0);
    });
  });

  btnX.addEventListener("click", close);
  btnPrev.addEventListener("click", function () { show(current - 1); });
  btnNext.addEventListener("click", function () { show(current + 1); });

  // A click on the overlay itself closes. Clicks on the figure, the image or
  // any control bubble from those elements instead, so they are left alone.
  lb.addEventListener("click", function (ev) {
    if (ev.target === lb) close();
  });

  document.addEventListener("keydown", function (ev) {
    if (lb.hidden) return;
    if (ev.key === "Escape") { ev.preventDefault(); close(); }
    else if (ev.key === "ArrowLeft") { ev.preventDefault(); show(current - 1); }
    else if (ev.key === "ArrowRight") { ev.preventDefault(); show(current + 1); }
  });
})();
