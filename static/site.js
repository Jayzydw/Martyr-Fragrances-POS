/* Small progressive enhancements; everything essential remains a normal Flask form. */
(() => {
  "use strict";

  const peso = (value) => new Intl.NumberFormat("en-PH", {
    style: "currency", currency: "PHP", minimumFractionDigits: 2
  }).format(Number.isFinite(value) ? value : 0);

  // Featured collection carousel. The imagery and buttons work without libraries.
  const slides = [...document.querySelectorAll(".hero-slide")];
  const dots = [...document.querySelectorAll("[data-dot]")];
  let current = 0;
  const show = (index) => {
    if (!slides.length) return;
    current = (index + slides.length) % slides.length;
    slides.forEach((slide, i) => {
      slide.classList.toggle("is-on", i === current);
      slide.setAttribute("aria-hidden", String(i !== current));
      slide.querySelectorAll("a").forEach((link) => { link.tabIndex = i === current ? 0 : -1; });
    });
    dots.forEach((dot, i) => {
      dot.classList.toggle("on", i === current);
      if (i === current) dot.setAttribute("aria-current", "true");
      else dot.removeAttribute("aria-current");
    });
  };
  if (slides.length) {
    show(0);
    document.querySelector("[data-prev]")?.addEventListener("click", () => show(current - 1));
    document.querySelector("[data-next]")?.addEventListener("click", () => show(current + 1));
    dots.forEach((dot) => dot.addEventListener("click", () => show(Number(dot.dataset.dot))));
    if (slides.length > 1 && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setInterval(() => { if (!document.hidden) show(current + 1); }, 7200);
    }
  }

  // Filtering preserves the original collection cards and URLs.
  const catalog = document.querySelector("[data-catalog]");
  if (catalog) {
    const cards = [...catalog.querySelectorAll(".scent")];
    const search = document.querySelector("[data-search]");
    const filters = [...document.querySelectorAll("[data-filter]")];
    const count = document.querySelector("[data-results-count]");
    const empty = document.querySelector("[data-empty-search]");
    let filter = "all";
    const update = () => {
      const term = (search?.value || "").trim().toLocaleLowerCase();
      let visible = 0;
      cards.forEach((card) => {
        const stock = Number(card.dataset.stock);
        const meetsFilter = filter === "all" || (filter === "available" ? stock > 0 : stock === 0);
        const showCard = meetsFilter && (card.dataset.name || "").includes(term);
        card.hidden = !showCard;
        if (showCard) visible += 1;
      });
      if (count) count.textContent = visible;
      if (empty) empty.hidden = visible !== 0;

    };
    search?.addEventListener("input", update);
    filters.forEach((button) => button.addEventListener("click", () => {
      filter = button.dataset.filter;
      filters.forEach((b) => b.classList.toggle("selected", b === button));
      update();
    }));
  }

  // Testimonials: a continuously scrolling, seamless carousel with manual controls.
  // Original cards remain in the HTML so the reviews are visible without JavaScript.
  const reviewSection = document.querySelector("[data-reviews-carousel]");
  const reviewTrack = reviewSection?.querySelector("[data-reviews-track]");
  if (reviewTrack) {
    const originals = [...reviewTrack.querySelectorAll(".review-card")];
    const controls = reviewSection.querySelector("[data-reviews-controls]");
    const toggle = reviewSection.querySelector("[data-review-toggle]");
    const status = reviewSection.querySelector("[data-reviews-status]");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (originals.length > 1) {
      originals.forEach((card) => {
        const clone = card.cloneNode(true);
        clone.setAttribute("aria-hidden", "true");
        clone.inert = true;
        reviewTrack.appendChild(clone);
      });
      reviewTrack.classList.add("is-marquee");
      reviewTrack.tabIndex = 0;
      reviewTrack.setAttribute("role", "region");
      reviewTrack.setAttribute("aria-label", "Customer reviews; use left and right arrows to browse");
      controls.hidden = false;

      let userPaused = false;
      let hoverPaused = false;
      let focusPaused = false;
      let visible = true;
      let resumeAfter = 0;
      let previousFrame = 0;
      let nudge = null;
      let cycleWidth = 0;
      let fractionalTravel = 0;
      const speed = 28; // pixels per second; deliberately gentle for easy reading.
      const updateWidth = () => { cycleWidth = reviewTrack.children[originals.length].offsetLeft - originals[0].offsetLeft; };
      const wrapPosition = () => {
        if (cycleWidth <= 0) return;
        if (reviewTrack.scrollLeft >= cycleWidth) reviewTrack.scrollLeft -= cycleWidth;
        else if (reviewTrack.scrollLeft < 0) reviewTrack.scrollLeft += cycleWidth;
      };
      const updateControls = () => {
        const stopped = userPaused || reducedMotion.matches;
        toggle.hidden = reducedMotion.matches;
        toggle.textContent = stopped ? "Play" : "Pause";
        toggle.setAttribute("aria-label", stopped ? "Resume automatic review scrolling" : "Pause automatic review scrolling");
        toggle.setAttribute("aria-pressed", String(userPaused));
        if (status) status.textContent = reducedMotion.matches ? "Use arrows to browse reviews" : (stopped ? "Autoplay paused · use arrows to browse" : (window.matchMedia("(pointer: coarse)").matches ? "Auto-scrolling · swipe to browse" : "Auto-scrolling · hover to pause"));
      };
      const easeOut = (t) => 1 - Math.pow(1 - t, 3);
      const frame = (time) => {
        const elapsed = Math.min(64, time - (previousFrame || time));
        previousFrame = time;
        if (nudge) {
          const t = Math.min(1, (time - nudge.start) / 520);
          const travelled = nudge.distance * easeOut(t);
          let next = reviewTrack.scrollLeft + travelled - nudge.previous;
          // When moving left, jump to the identical set before crossing the start.
          if (next < 0) next += cycleWidth;
          reviewTrack.scrollLeft = next;
          wrapPosition();
          nudge.previous = travelled;
          if (t === 1) nudge = null;
        } else if (!document.hidden && visible && !userPaused && !hoverPaused && !focusPaused && !reducedMotion.matches && time >= resumeAfter) {
          // Preserve subpixel movement so slow scrolling works in browsers that
          // round scrollLeft to whole pixels (otherwise it can freeze at 0).
          fractionalTravel += speed * elapsed / 1000;
          const pixels = Math.floor(fractionalTravel);
          if (pixels) {
            fractionalTravel -= pixels;
            reviewTrack.scrollLeft += pixels;
            wrapPosition();
          }
        }
        requestAnimationFrame(frame);
      };
      const step = (direction) => {
        updateWidth();
        if (!cycleWidth) return;
        // Keep the experience readable after a user interacts with the carousel.
        resumeAfter = performance.now() + 5200;
        const cardGap = parseFloat(getComputedStyle(reviewTrack).columnGap) || 0;
        const distance = direction * (originals[0].getBoundingClientRect().width + cardGap);
        if (reducedMotion.matches) {
          let next = reviewTrack.scrollLeft + distance;
          if (next < 0) next += cycleWidth;
          if (next >= cycleWidth) next -= cycleWidth;
          reviewTrack.scrollLeft = next;
        } else {
          nudge = { start: performance.now(), distance, previous: 0 };
        }
      };
      reviewSection.querySelector("[data-review-prev]")?.addEventListener("click", () => step(-1));
      reviewSection.querySelector("[data-review-next]")?.addEventListener("click", () => step(1));
      toggle?.addEventListener("click", () => { userPaused = !userPaused; updateControls(); });
      reviewTrack.addEventListener("mouseenter", () => { hoverPaused = true; });
      reviewTrack.addEventListener("mouseleave", () => { hoverPaused = false; resumeAfter = performance.now() + 700; });
      reviewTrack.addEventListener("focusin", () => { focusPaused = true; });
      reviewTrack.addEventListener("focusout", () => { focusPaused = false; resumeAfter = performance.now() + 1200; });
      reviewTrack.addEventListener("keydown", (event) => {
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
          event.preventDefault();
          step(event.key === "ArrowLeft" ? -1 : 1);
        }
      });
      reviewTrack.addEventListener("pointerdown", () => { resumeAfter = performance.now() + 6500; });
      reviewTrack.addEventListener("wheel", () => { resumeAfter = performance.now() + 3500; }, { passive: true });
      if ("IntersectionObserver" in window) {
        new IntersectionObserver((entries) => { visible = entries[0]?.isIntersecting ?? true; }, { threshold: .08 }).observe(reviewTrack);
      }
      if ("ResizeObserver" in window) new ResizeObserver(updateWidth).observe(reviewTrack);
      else window.addEventListener("resize", updateWidth, { passive: true });
      reducedMotion.addEventListener?.("change", updateControls);
      updateWidth();
      updateControls();
      requestAnimationFrame(frame);
    }
  }

  // Checkout hides cash-only controls when a demo digital method is chosen.
  document.querySelectorAll("[data-payment-form]").forEach((form) => {
    const cashField = form.querySelector("[data-cash-field]");
    const tendered = cashField?.querySelector("input");
    const changeText = form.querySelector("[data-payment-change]");
    const total = Number(form.querySelector("input[name=tendered]")?.defaultValue || 0);
    const update = () => {
      const cash = form.querySelector('input[name="payment"]:checked')?.value === "Cash";
      if (cashField) cashField.hidden = !cash;
      if (tendered) tendered.required = cash;
      if (changeText) {
        changeText.hidden = !cash;
        changeText.textContent = "Expected change: " + peso(Math.max(0, Number(tendered?.value || 0) - total));
      }
    };
    form.addEventListener("change", update);
    tendered?.addEventListener("input", update);
    update();
  });

  // In-store register: dynamic product lines, quantity limits and live totals.
  const register = document.querySelector("[data-register-form]");
  if (register) {
    const linesContainer = register.querySelector("[data-register-lines]");
    const template = document.querySelector("#register-line-template");
    const add = register.querySelector("[data-add-line]");
    const totalElement = register.querySelector("[data-register-total]");
    const countElement = register.querySelector("[data-register-count]");
    const cashField = register.querySelector("[data-cash-field]");
    const cashInput = cashField?.querySelector("input");
    const changeElement = register.querySelector("[data-register-change]");
    const changeWrap = register.querySelector("[data-change-wrap]");
    const update = () => {
      let total = 0;
      let count = 0;
      const lines = [...linesContainer.querySelectorAll(".register-line")];
      lines.forEach((line) => {
        const select = line.querySelector(".register-product");
        const qtyInput = line.querySelector(".register-qty");
        const option = select?.selectedOptions[0];
        const stock = Number(option?.dataset.stock || 0);
        const price = Number(option?.dataset.price || 0);
        if (qtyInput) qtyInput.max = String(stock);
        const qty = Math.max(0, Number(qtyInput?.value || 0));
        total += price * qty;
        count += qty;
        const priceLabel = line.querySelector(".register-line-price");
        if (priceLabel) priceLabel.textContent = peso(qty * price);
        const remove = line.querySelector(".remove-register-line");
        if (remove) remove.disabled = lines.length === 1;
      });
      if (totalElement) totalElement.textContent = peso(total);
      if (countElement) countElement.textContent = `${count} bottle${count === 1 ? "" : "s"}`;
      const cash = register.querySelector('input[name="payment"]:checked')?.value === "Cash";
      if (cashField) cashField.hidden = !cash;
      if (cashInput) cashInput.required = cash;
      if (changeWrap) changeWrap.hidden = !cash;
      if (changeElement) changeElement.textContent = peso(Math.max(0, Number(cashInput?.value || 0) - total));
    };
    add?.addEventListener("click", () => {
      if (!template) return;
      linesContainer.appendChild(template.content.cloneNode(true));
      update();
    });
    linesContainer?.addEventListener("click", (event) => {
      const button = event.target.closest(".remove-register-line");
      if (button && linesContainer.querySelectorAll(".register-line").length > 1) {
        button.closest(".register-line")?.remove();
        update();
      }
    });
    register.addEventListener("input", update);
    register.addEventListener("change", update);
    update();
  }

  // Read the new image locally so the admin sees the selection before saving.
  const imageInput = document.querySelector("[data-image-input]");
  const preview = document.querySelector("[data-image-preview]");
  imageInput?.addEventListener("change", () => {
    const file = imageInput.files?.[0];
    if (!file || !preview) return;
    if (!/^image\/(jpeg|png|webp|gif)$/.test(file.type) || file.size > 5 * 1024 * 1024) {
      preview.textContent = "Select a JPG, PNG, WEBP or GIF under 5 MB.";
      imageInput.value = "";
      return;
    }
    const url = URL.createObjectURL(file);
    const image = document.createElement("img");
    image.src = url;
    image.alt = "New product image preview";
    image.onload = () => URL.revokeObjectURL(url);
    preview.replaceChildren(image);
  });
})();
