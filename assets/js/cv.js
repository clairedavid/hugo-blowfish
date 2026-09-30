/* CV page: mark the section you are currently reading in the left rail.

   A scroll listener rather than IntersectionObserver, because the question
   here is "which section is the page showing now", not "is this element
   visible". Sections are tall and several are on screen at once, so the answer
   is the last heading to have passed the top of the viewport, which a
   threshold test reads off directly and an observer only reaches indirectly.

   Bold is the only signal: no colour change, by design.
   Nothing is fetched at runtime. */
(function () {
  "use strict";

  var root = document.getElementById("cv");
  if (!root) return;

  var links = Array.prototype.slice.call(root.querySelectorAll("[data-cv-link]"));
  if (!links.length) return;

  var items = [];
  links.forEach(function (a) {
    var el = document.getElementById(a.getAttribute("data-cv-link"));
    if (el) items.push({ link: a, el: el });
  });
  if (!items.length) return;

  var OFFSET = 140;   // a heading counts as "reached" this far down the viewport
  var current = null;

  function update() {
    var pick = items[0];
    for (var i = 0; i < items.length; i++) {
      if (items[i].el.getBoundingClientRect().top <= OFFSET) pick = items[i];
    }
    // At the very bottom the last section may be too short to cross the
    // threshold, so it would never light up. Hand it the last one instead.
    var doc = document.documentElement;
    if (window.innerHeight + window.scrollY >= doc.scrollHeight - 2) {
      pick = items[items.length - 1];
    }
    if (pick === current) return;
    if (current) current.link.classList.remove("is-current");
    pick.link.classList.add("is-current");
    current = pick;
  }

  var ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(function () { update(); ticking = false; });
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll, { passive: true });

  // Close the phone disclosure after a jump, so the content is not left behind
  // a expanded list.
  var jump = root.querySelector(".cv-jump");
  if (jump) {
    jump.addEventListener("click", function (ev) {
      if (ev.target.tagName === "A") jump.open = false;
    });
  }

  update();
})();
