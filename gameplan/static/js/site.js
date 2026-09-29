document.addEventListener('DOMContentLoaded', () => {
  const menuButton = document.querySelector('[data-menu-toggle]');
  const primaryNav = document.querySelector('[data-primary-nav]');

  const closeMobileMenu = () => {
    if (!menuButton || !primaryNav) return;
    menuButton.setAttribute('aria-expanded', 'false');
    primaryNav.classList.remove('open');
    document.body.classList.remove('menu-open');
  };

  menuButton?.addEventListener('click', () => {
    const open = menuButton.getAttribute('aria-expanded') !== 'true';
    menuButton.setAttribute('aria-expanded', String(open));
    primaryNav?.classList.toggle('open', open);
    document.body.classList.toggle('menu-open', open);
  });

  primaryNav?.querySelectorAll('a').forEach((link) => link.addEventListener('click', closeMobileMenu));
  window.addEventListener('resize', () => { if (window.innerWidth > 900) closeMobileMenu(); });

  document.addEventListener('click', (event) => {
    document.querySelectorAll('[data-account-menu][open]').forEach((menu) => {
      if (!menu.contains(event.target)) menu.removeAttribute('open');
    });
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    closeMobileMenu();
    document.querySelectorAll('[data-account-menu][open]').forEach((menu) => menu.removeAttribute('open'));
  });

  document.querySelectorAll('[data-hero-carousel]').forEach((carousel) => {
    const slides = [...carousel.querySelectorAll('[data-hero-slide]')];
    const dots = [...carousel.querySelectorAll('[data-hero-dot]')];
    if (slides.length < 2) return;

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
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
        slide.classList.toggle('active', active);
        slide.setAttribute('aria-hidden', String(!active));
      });
      dots.forEach((dot, dotIndex) => {
        const active = dotIndex === current;
        dot.classList.toggle('active', active);
        dot.setAttribute('aria-current', String(active));
      });
      if (restart) startAutoplay();
    };

    carousel.querySelector('[data-hero-previous]')?.addEventListener('click', () => show(current - 1));
    carousel.querySelector('[data-hero-next]')?.addEventListener('click', () => show(current + 1));
    dots.forEach((dot) => dot.addEventListener('click', () => show(Number(dot.dataset.heroDot))));
    carousel.addEventListener('mouseenter', () => { hovering = true; stopAutoplay(); });
    carousel.addEventListener('mouseleave', () => { hovering = false; startAutoplay(); });
    carousel.addEventListener('keydown', (event) => {
      if (/^(INPUT|SELECT|BUTTON)$/.test(event.target.tagName)) return;
      if (event.key === 'ArrowLeft') { event.preventDefault(); show(current - 1); }
      if (event.key === 'ArrowRight') { event.preventDefault(); show(current + 1); }
    });
    carousel.addEventListener('pointerdown', (event) => {
      if (event.pointerType === 'mouse') return;
      pointerStart = { x: event.clientX, y: event.clientY };
    }, { passive: true });
    carousel.addEventListener('pointerup', (event) => {
      if (!pointerStart) return;
      const dx = event.clientX - pointerStart.x;
      const dy = event.clientY - pointerStart.y;
      pointerStart = null;
      if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.2) show(current + (dx < 0 ? 1 : -1));
    }, { passive: true });
    carousel.addEventListener('pointercancel', () => { pointerStart = null; });
    document.addEventListener('visibilitychange', () => document.hidden ? stopAutoplay() : startAutoplay());
    startAutoplay();
  });

  const dateInput = document.querySelector('.hero-search input[type="date"]');
  if (dateInput && !dateInput.value) {
    const today = new Date();
    const localToday = new Date(today.getTime() - today.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
    dateInput.min = localToday;
    dateInput.value = localToday;
  }

  document.querySelectorAll('.heart').forEach((button) => {
    button.addEventListener('click', () => {
      const saved = button.classList.toggle('saved');
      button.innerHTML = saved ? '&#9829;' : '&#9825;';
      button.setAttribute('aria-pressed', String(saved));
    });
  });

  document.querySelectorAll('a[href="#"]').forEach((link) => {
    link.addEventListener('click', (event) => event.preventDefault());
  });

  document.querySelectorAll('form[data-template-placeholder="true"]').forEach((form) => {
    form.addEventListener('submit', (event) => event.preventDefault());
  });
});
