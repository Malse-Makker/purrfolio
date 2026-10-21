/* Purrfolio — kleine, afhankelijkheidsloze interactie. */
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.remove("no-js");

  /* ── Thema ─────────────────────────────────────────────────────────────── */
  var toggle = document.querySelector(".theme-toggle");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var next = root.dataset.theme === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      try { localStorage.setItem("theme", next); } catch (e) { /* privémodus */ }
    });
  }

  /* ── Foto's zacht laten verschijnen zodra ze geladen zijn ─────────────── */
  function markLoaded(img) { img.classList.add("is-loaded"); }
  document.querySelectorAll("img.fade").forEach(function (img) {
    if (img.complete && img.naturalWidth) markLoaded(img);
    else {
      img.addEventListener("load", function () { markLoaded(img); }, { once: true });
      img.addEventListener("error", function () { markLoaded(img); }, { once: true });
    }
  });

  /* ── Blokken zacht in beeld laten schuiven bij het scrollen ──────────── */
  var reveals = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("is-in"); io.unobserve(en.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px" });
    reveals.forEach(function (el) { io.observe(el); });
  } else {
    reveals.forEach(function (el) { el.classList.add("is-in"); });
  }

  /* ── Nav wordt dicht zodra je voorbij de hero scrolt ──────────────────── */
  var nav = document.querySelector(".nav");
  var hero = document.querySelector(".hero");
  if (nav && hero) {
    var onScroll = function () {
      nav.classList.toggle("is-solid", window.scrollY > hero.offsetHeight - nav.offsetHeight - 10);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  /* ── Lightbox ──────────────────────────────────────────────────────────── */
  var dataEl = document.getElementById("photo-data");
  var lb = document.getElementById("lightbox");
  if (!dataEl || !lb) return;

  var photos = JSON.parse(dataEl.textContent);
  var img = lb.querySelector(".lb-img");
  var counter = lb.querySelector(".lb-counter");
  var exif = lb.querySelector(".lb-exif");
  var original = lb.querySelector(".lb-original");
  var current = -1;
  var lastFocus = null;

  function preload(i) {
    var p = photos[(i + photos.length) % photos.length];
    if (p) { var im = new Image(); im.src = p.full; }
  }

  function renderExif(p) {
    exif.textContent = "";
    (p.exif || []).forEach(function (item) {
      var span = document.createElement("span");
      var icon = document.createElement("i");
      icon.className = "fa-solid " + item[0];
      icon.setAttribute("aria-hidden", "true");
      span.appendChild(icon);
      span.appendChild(document.createTextNode(item[1]));
      exif.appendChild(span);
    });
  }

  function show(i, push) {
    i = (i + photos.length) % photos.length;
    var p = photos[i];
    var first = current === -1;
    current = i;
    img.classList.add("is-switching");
    var swap = function () {
      img.src = p.full;
      img.alt = p.alt;
      img.onload = function () { img.classList.remove("is-switching"); };
    };
    first ? swap() : setTimeout(swap, 120);
    counter.textContent = (i + 1) + " / " + photos.length;
    original.href = p.orig;
    renderExif(p);
    preload(i + 1);
    preload(i - 1);
    var hash = "#photo-" + (i + 1);
    if (push) history.pushState({ lb: i }, "", hash);
    else history.replaceState({ lb: i }, "", hash);
  }

  function open(i) {
    lastFocus = document.activeElement;
    lb.classList.add("is-open");
    lb.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    show(i, true);
    lb.querySelector(".lb-close").focus();
  }

  function close(fromHistory) {
    if (!lb.classList.contains("is-open")) return;
    lb.classList.remove("is-open");
    lb.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    current = -1;
    if (!fromHistory && location.hash.indexOf("#photo-") === 0) history.back();
    if (lastFocus) lastFocus.focus();
  }

  document.querySelectorAll(".photo").forEach(function (el, i) {
    el.addEventListener("click", function (e) { e.preventDefault(); open(i); });
  });
  lb.querySelector(".lb-close").addEventListener("click", function () { close(false); });
  lb.querySelector(".lb-prev").addEventListener("click", function () { show(current - 1); });
  lb.querySelector(".lb-next").addEventListener("click", function () { show(current + 1); });
  lb.querySelector(".lb-stage").addEventListener("click", function (e) {
    if (e.target === e.currentTarget) close(false);
  });

  document.addEventListener("keydown", function (e) {
    if (!lb.classList.contains("is-open")) return;
    if (e.key === "Escape") close(false);
    else if (e.key === "ArrowLeft") show(current - 1);
    else if (e.key === "ArrowRight") show(current + 1);
  });

  // Vegen op touch
  var sx = null, sy = null;
  lb.addEventListener("touchstart", function (e) {
    if (e.touches.length !== 1) return;
    sx = e.touches[0].clientX; sy = e.touches[0].clientY;
  }, { passive: true });
  lb.addEventListener("touchend", function (e) {
    if (sx === null) return;
    var dx = e.changedTouches[0].clientX - sx;
    var dy = e.changedTouches[0].clientY - sy;
    sx = sy = null;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) show(current + (dx < 0 ? 1 : -1));
    else if (dy > 90 && Math.abs(dy) > Math.abs(dx)) close(false);   // omlaag vegen sluit
  }, { passive: true });

  // Terugknop van de browser sluit de lightbox; #photo-N opent direct
  window.addEventListener("popstate", function () {
    var m = location.hash.match(/^#photo-(\d+)$/);
    if (m) {
      if (!lb.classList.contains("is-open")) { lb.classList.add("is-open"); document.body.style.overflow = "hidden"; }
      show(parseInt(m[1], 10) - 1);
    } else close(true);
  });
  var start = location.hash.match(/^#photo-(\d+)$/);
  if (start) { history.replaceState(null, "", location.pathname); open(parseInt(start[1], 10) - 1); }
})();
