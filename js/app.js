/* =============================================
   FLOWERS FOREVER - Main App JS
   ============================================= */

(function () {
  'use strict';

  /* ---- Sticky Header ---- */
  const header = document.getElementById('site-header');
  if (header) {
    window.addEventListener('scroll', () => {
      header.classList.toggle('scrolled', window.scrollY > 20);
    });
  }

  /* ---- Mobile Nav ---- */
  const hamburger = document.getElementById('hamburger');
  const mainNav = document.getElementById('main-nav');
  if (hamburger && mainNav) {
    hamburger.addEventListener('click', () => {
      const open = mainNav.classList.toggle('open');
      hamburger.setAttribute('aria-expanded', open);
    });

    // Close nav on link click
    mainNav.querySelectorAll('.nav-link').forEach(link => {
      link.addEventListener('click', () => mainNav.classList.remove('open'));
    });

    // Close on outside click
    document.addEventListener('click', e => {
      if (!hamburger.contains(e.target) && !mainNav.contains(e.target)) {
        mainNav.classList.remove('open');
      }
    });
  }

  /* ---- Plan Filter ---- */
  const filterBtns = document.querySelectorAll('.filter-btn');
  const planCards  = document.querySelectorAll('.plan-card');

  filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      filterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const filter = btn.dataset.filter;
      planCards.forEach(card => {
        if (filter === 'all' || card.dataset.category === filter) {
          card.classList.remove('hidden');
          // Re-trigger animation
          card.style.animation = 'none';
          card.offsetHeight; // reflow
          card.style.animation = '';
        } else {
          card.classList.add('hidden');
        }
      });
    });
  });

  /* ---- Subscription Selection → Checkout ---- */
  const planSelectBtns = document.querySelectorAll('.plan-select-btn');

  planSelectBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const planData = {
        plan:   btn.dataset.plan,
        name:   btn.dataset.planName,
        price:  btn.dataset.planPrice,
        period: btn.dataset.planPeriod,
        code:   btn.dataset.planCode,
      };

      // Save to sessionStorage for checkout page
      sessionStorage.setItem('selectedPlan', JSON.stringify(planData));

      // Update cart count
      updateCartCount(1);

      // Navigate to checkout
      window.location.href = 'checkout.html';
    });
  });

  /* ---- Cart Count ---- */
  function updateCartCount(count) {
    const cartCount = document.getElementById('cart-count');
    if (cartCount) {
      cartCount.textContent = count;
      cartCount.style.transform = 'scale(1.3)';
      setTimeout(() => { cartCount.style.transform = ''; }, 300);
    }
  }

  // Restore cart count from session
  const savedPlan = sessionStorage.getItem('selectedPlan');
  if (savedPlan) updateCartCount(1);

  /* ---- Smooth scroll for anchor links ---- */
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', e => {
      const target = document.querySelector(anchor.getAttribute('href'));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });

  /* ---- Animate on Scroll ---- */
  const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px',
  };

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, observerOptions);

  document.querySelectorAll(
    '.plan-card, .benefit-card, .step, .testimonial-card'
  ).forEach(el => {
    el.classList.add('fade-in-ready');
    observer.observe(el);
  });

})();
