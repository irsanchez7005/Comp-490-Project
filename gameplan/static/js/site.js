document.addEventListener("DOMContentLoaded", () => {
  const menuButton = document.querySelector("[data-menu-toggle]");
  const primaryNav = document.querySelector("[data-primary-nav]");

  const closeMobileMenu = () => {
    if (!menuButton || !primaryNav) return;
    menuButton.setAttribute("aria-expanded", "false");
    primaryNav.classList.remove("open");
    document.body.classList.remove("menu-open");
  };

  menuButton?.addEventListener("click", () => {
    const open = menuButton.getAttribute("aria-expanded") !== "true";
    menuButton.setAttribute("aria-expanded", String(open));
    primaryNav?.classList.toggle("open", open);
    document.body.classList.toggle("menu-open", open);
  });

  primaryNav
    ?.querySelectorAll("a")
    .forEach((link) => link.addEventListener("click", closeMobileMenu));
  window.addEventListener("resize", () => {
    if (window.innerWidth > 900) closeMobileMenu();
  });

  document.addEventListener("click", (event) => {
    document.querySelectorAll("[data-account-menu][open]").forEach((menu) => {
      if (!menu.contains(event.target)) menu.removeAttribute("open");
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    closeMobileMenu();
    document
      .querySelectorAll("[data-account-menu][open]")
      .forEach((menu) => menu.removeAttribute("open"));
  });

  document.querySelectorAll("[data-hero-carousel]").forEach((carousel) => {
    const slides = [...carousel.querySelectorAll("[data-hero-slide]")];
    const dots = [...carousel.querySelectorAll("[data-hero-dot]")];
    if (slides.length < 2) return;

    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    let current = 0;
    let timer = null;
    let hovering = false;
    let pointerStart = null;

    const stopAutoplay = () => {
      if (timer) window.clearInterval(timer);
      timer = null;
    };

    const startAutoplay = () => {
      stopAutoplay();
      if (reducedMotion || hovering || document.hidden) return;
      timer = window.setInterval(() => show(current + 1, false), 5500);
    };

    const show = (index, restart = true) => {
      current = (index + slides.length) % slides.length;
      slides.forEach((slide, slideIndex) => {
        const active = slideIndex === current;
        slide.classList.toggle("active", active);
        slide.setAttribute("aria-hidden", String(!active));
      });
      dots.forEach((dot, dotIndex) => {
        const active = dotIndex === current;
        dot.classList.toggle("active", active);
        dot.setAttribute("aria-current", String(active));
      });
      if (restart) startAutoplay();
    };

    carousel
      .querySelector("[data-hero-previous]")
      ?.addEventListener("click", () => show(current - 1));
    carousel
      .querySelector("[data-hero-next]")
      ?.addEventListener("click", () => show(current + 1));
    dots.forEach((dot) =>
      dot.addEventListener("click", () => show(Number(dot.dataset.heroDot))),
    );
    carousel.addEventListener("mouseenter", () => {
      hovering = true;
      stopAutoplay();
    });
    carousel.addEventListener("mouseleave", () => {
      hovering = false;
      startAutoplay();
    });
    carousel.addEventListener("keydown", (event) => {
      if (/^(INPUT|SELECT|BUTTON)$/.test(event.target.tagName)) return;
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        show(current - 1);
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        show(current + 1);
      }
    });
    carousel.addEventListener(
      "pointerdown",
      (event) => {
        if (event.pointerType === "mouse") return;
        pointerStart = { x: event.clientX, y: event.clientY };
      },
      { passive: true },
    );
    carousel.addEventListener(
      "pointerup",
      (event) => {
        if (!pointerStart) return;
        const dx = event.clientX - pointerStart.x;
        const dy = event.clientY - pointerStart.y;
        pointerStart = null;
        if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.2)
          show(current + (dx < 0 ? 1 : -1));
      },
      { passive: true },
    );
    carousel.addEventListener("pointercancel", () => {
      pointerStart = null;
    });
    document.addEventListener("visibilitychange", () =>
      document.hidden ? stopAutoplay() : startAutoplay(),
    );
    startAutoplay();
  });

  const dateInput = document.querySelector('.hero-search input[type="date"]');
  if (dateInput && !dateInput.value) {
    const today = new Date();
    const localToday = new Date(
      today.getTime() - today.getTimezoneOffset() * 60000,
    )
      .toISOString()
      .slice(0, 10);
    dateInput.min = localToday;
    dateInput.value = localToday;
  }

  document.querySelectorAll(".heart").forEach((button) => {
    button.addEventListener("click", () => {
      const saved = button.classList.toggle("saved");
      button.innerHTML = saved ? "&#9829;" : "&#9825;";
      button.setAttribute("aria-pressed", String(saved));
    });
  });

  document.querySelectorAll(".btn-read-more").forEach((button) => {
    const text = button.closest(".course-body")?.querySelector(".course-desc");
    if (!text) return;
    button.addEventListener("click", () => {
      const expanded = text.classList.toggle("expanded");
      button.textContent = expanded ? "Read Less" : "Read More";
      button.setAttribute("aria-expanded", String(expanded));
    });
  });

  document.querySelectorAll('a[href="#"]').forEach((link) => {
    link.addEventListener("click", (event) => event.preventDefault());
  });

  document
    .querySelectorAll('form[data-template-placeholder="true"]')
    .forEach((form) => {
      form.addEventListener("submit", (event) => event.preventDefault());
    });
});
/* */
document.addEventListener("DOMContentLoaded", () => {
  const dialog = document.getElementById("booking-dialog");
  if (!dialog) return;
  const courseName = document.getElementById("booking-course-name");
  const timeLabel = document.getElementById("booking-time-label");
  const detailsTime = document.getElementById("booking-details-time");

  const openBooking = (card) => {
    const course = card.querySelector(".course-info h2").textContent.trim();
    const time = card.querySelector("time").textContent.trim();

    courseName.textContent = course;
    timeLabel.textContent = time;
    detailsTime.textContent = time;
    dialog.showModal();
  };

  document.querySelectorAll(".tee-card button").forEach((button) => {
    button.addEventListener("click", () =>
      openBooking(button.closest(".tee-card")),
    );
  });

  dialog.querySelectorAll("[data-close-booking]").forEach((button) => {
    button.addEventListener("click", () => dialog.close());
  });

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
});
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-autocomplete]").forEach((input) => {
    const wrap = input.closest(".search-wrap");
    if (!wrap) return;
    const panel = document.createElement("div");
    panel.className = "search-results";
    panel.hidden = true;
    wrap.appendChild(panel);

    let timer;
    input .addEventListener("input", () => {
      clearTimeout(timer);
      const q = input.value.trim();
      if (!q) {
        panel.hidden = true;
        return;
      }
   timer = setTimeout(() => {
        fetch("/search/?q=" + encodeURIComponent(q))
          .then(r => r.json())
          .then(data => {
            if (!data.results.length) {
              panel.innerHTML = '<p class="search-empty">No courses found</p>';
            } else {
              // carry the date along if the form has one
              const dateField = input.form && input.form.querySelector('input[type="date"]');
              const extra = dateField && dateField.value ? "?date=" + dateField.value : "";

              panel.innerHTML = data.results.map(r =>
                `<a href="/facilities/${r.id}/${extra}">
                   <strong>${r.name}</strong><span>${r.city}</span>
                 </a>`
              ).join("");
            }
            panel.hidden = false;
          });
      }, 150);
    });
    document.addEventListener("click", (event) => {
      if (!wrap.contains(event.target)) panel.hidden = true;
    });
  });
});

/* Verification code lock: count down, then let the user try again */
document.addEventListener("DOMContentLoaded", () => {
  const lock = document.getElementById("code-lock");
  if (!lock) return;
  const timer = document.getElementById("code-lock-timer");
  const button = document.getElementById("verify-button");
  let seconds = Number(lock.dataset.seconds);

  const show = () => {
    const m = Math.floor(seconds / 60);
    const s = String(seconds % 60).padStart(2, "0");
    timer.textContent = m + ":" + s;
  };

  show();
  const tick = setInterval(() => {
    seconds -= 1;
    if (seconds <= 0) {
      clearInterval(tick);
      lock.remove();
      button.disabled = false;
      return;
    }
    show();
  }, 1000);
});
