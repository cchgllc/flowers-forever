/* =============================================
   FLOWERS FOREVER - Checkout JS (Recurly.js)
   ============================================= */

(function () {
  'use strict';

  /* ----------------------------------------
     1. POPULATE ORDER SUMMARY FROM SESSION
  ---------------------------------------- */
  const savedPlan = sessionStorage.getItem('selectedPlan');
  let planData = {
    plan:   '1399',
    name:   'Classic Bouquet',
    price:  '50.00',
    period: 'Monthly',
    code:   '1399',
  };

  if (savedPlan) {
    try {
      planData = JSON.parse(savedPlan);
    } catch (e) {
      console.warn('Could not parse selected plan from session.');
    }
  }

  // Update summary UI
  const el = id => document.getElementById(id);

  el('summary-plan-name').textContent  = planData.name;
  el('summary-plan-period').textContent = planData.period + ' Subscription';
  el('summary-price').textContent      = '$' + planData.price;
  el('summary-total').textContent      = '$' + planData.price;
  el('summary-renewal-price').textContent = '$' + planData.price;

  /* ----------------------------------------
     2. INITIALIZE RECURLY.JS
     NOTE: Replace 'YOUR_RECURLY_PUBLIC_KEY' with
     your actual Recurly public API key from
     the Recurly Admin Console → API Credentials.
  ---------------------------------------- */
  const RECURLY_PUBLIC_KEY = 'ewr1-4PJDOk2BuPIEX2gEhM0Kru';

  // Only initialize if the recurly global is available
  if (typeof recurly === 'undefined') {
    console.warn(
      'Recurly.js not loaded. Make sure you have a valid Recurly account ' +
      'and have included the script at https://js.recurly.com/v4/recurly.js'
    );
    showDevNotice();
  } else {
    initRecurly();
  }

  function initRecurly() {
    // Shared iframe styles — Recurly applies these inside each hosted iframe.
    const iframeStyle = {
      fontFamily: "'Inter', system-ui, -apple-system, sans-serif",
      fontSize:   '15px',
      fontWeight: '400',
      color:      '#1a1a2e',
      placeholder: { color: '#9ca3af' },
    };

    recurly.configure({
      publicKey: RECURLY_PUBLIC_KEY,
      fields: {
        // Each `selector` targets the host <div> by its id.
        // Recurly injects a sized <iframe> into these containers.
        number: { selector: '#recurly-number', style: iframeStyle },
        month:  { selector: '#recurly-month',  style: iframeStyle },
        year:   { selector: '#recurly-year',   style: iframeStyle },
        cvv:    { selector: '#recurly-cvv',    style: { ...iframeStyle, placeholder: { color: '#9ca3af' } } },
      },
    });

    // ── Payment method tabs ────────────────────────────────────────────────
    initPaymentTabs();

    // ── Apple Pay ──────────────────────────────────────────────────────────
    initApplePay();

    // Real-time validation feedback — only show error after user leaves the field
    recurly.on('change', function (state) {
      ['number', 'month', 'year', 'cvv'].forEach(field => {
        const fieldState = state.fields[field];
        const errorEl    = el(field + '-error');
        if (!errorEl) return;
        if (fieldState && !fieldState.focus && !fieldState.valid && fieldState.empty === false) {
          errorEl.textContent = getFieldError(field);
        } else {
          errorEl.textContent = '';
        }
      });
    });
  }

  /* ----------------------------------------
     2b. PAYMENT METHOD TABS
     Switches between Credit Card, ACH and SEPA panels.
     Active tab is stored in window._activePayTab so the
     submit handler knows which token flow to invoke.
  ---------------------------------------- */
  window._activePayTab = 'card'; // default

  function initPaymentTabs() {
    const tabs   = document.querySelectorAll('.pay-tab');
    const panels = document.querySelectorAll('.pay-panel');
    if (!tabs.length) return;

    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        const target = tab.dataset.tab;
        window._activePayTab = target;

        // Update tab active state
        tabs.forEach(function (t) {
          t.classList.toggle('pay-tab--active', t === tab);
          t.setAttribute('aria-selected', t === tab ? 'true' : 'false');
        });

        // Show/hide panels
        panels.forEach(function (panel) {
          const show = panel.id === 'panel-' + target;
          panel.style.display = show ? '' : 'none';
          panel.classList.toggle('pay-panel--active', show);
        });

        // Clear any prior payment errors when switching tabs
        hideMessages();
      });
    });
  }

  /* ----------------------------------------
     2c. BANK ACCOUNT TOKEN (ACH / SEPA)
     Uses recurly.bankAccount.token() with plain
     form inputs — no hosted iframes needed.
     Recurly docs: /recurly-subscriptions/docs/bank-accounts-us-iban-bacs-becs
  ---------------------------------------- */
  function getBankAccountData(type) {
    if (type === 'ach') {
      return {
        name_on_account:              (el('ach-name')           || {}).value || '',
        routing_number:               (el('ach-routing')        || {}).value || '',
        account_number:               (el('ach-account')        || {}).value || '',
        account_number_confirmation:  (el('ach-account-confirm')|| {}).value || '',
        account_type:                 (el('ach-type')           || {}).value || 'checking',
        // billing address pulled from delivery fields
        address1:    (el('billing-address1') || {}).value || '',
        city:        (el('billing-city')     || {}).value || '',
        state:       (el('billing-state')    || {}).value || '',
        postal_code: (el('billing-zip')      || {}).value || '',
        country:     'US',
      };
    }
    if (type === 'sepa') {
      return {
        name_on_account: (el('sepa-name')    || {}).value || '',
        iban:            (el('sepa-iban')    || {}).value.replace(/\s/g, '') || '',
        country:         (el('sepa-country') || {}).value || 'DE',
      };
    }
    return null;
  }

  function validateBankFields(type) {
    let ok = true;

    function bankErr(inputId, errId, msg) {
      const input = el(inputId);
      const errEl = el(errId);
      if (!input || !input.value.trim()) {
        if (errEl) errEl.textContent = msg;
        if (input) input.classList.add('input-error');
        ok = false;
      } else {
        if (errEl) errEl.textContent = '';
        if (input) input.classList.remove('input-error');
      }
    }

    if (type === 'ach') {
      bankErr('ach-name',           'ach-name-error',    'Name on account is required.');
      bankErr('ach-routing',        'ach-routing-error', 'Routing number is required.');
      bankErr('ach-account',        'ach-account-error', 'Account number is required.');
      bankErr('ach-account-confirm','ach-confirm-error', 'Please confirm your account number.');

      const acct    = (el('ach-account')        || {}).value || '';
      const confirm = (el('ach-account-confirm')|| {}).value || '';
      if (acct && confirm && acct !== confirm) {
        const errEl = el('ach-confirm-error');
        if (errEl) errEl.textContent = 'Account numbers do not match.';
        const inp = el('ach-account-confirm');
        if (inp) inp.classList.add('input-error');
        ok = false;
      }
    }

    if (type === 'sepa') {
      bankErr('sepa-name', 'sepa-name-error', 'Name on account is required.');
      bankErr('sepa-iban', 'sepa-iban-error', 'IBAN is required.');

      const iban = ((el('sepa-iban') || {}).value || '').replace(/\s/g, '');
      if (iban && !/^[A-Z]{2}[0-9A-Z]{13,32}$/.test(iban.toUpperCase())) {
        const errEl = el('sepa-iban-error');
        if (errEl) errEl.textContent = 'Please enter a valid IBAN.';
        const inp = el('sepa-iban');
        if (inp) inp.classList.add('input-error');
        ok = false;
      }
    }

    return ok;
  }

  function tokenizeBankAccount(type, callback) {
    syncBillingAddressToRecurly();
    const data = getBankAccountData(type);
    if (!data) return callback(new Error('Unknown bank account type.'), null);

    recurly.bankAccount.token(data, function (err, token) {
      if (err) return callback(err, null);
      callback(null, token);
    });
  }

  /* ----------------------------------------
     2e. APPLE PAY
     Recurly.js handles device/browser detection.
     The button is hidden by default and only shown
     when applePay.ready() fires (Safari + capable device).
  ---------------------------------------- */
  function initApplePay() {
    const applePayContainer = el('apple-pay-container');
    const applePayBtn       = el('apple-pay-btn');
    if (!applePayContainer || !applePayBtn) return;

    const applePay = recurly.ApplePay({
      country:  'US',
      currency: 'USD',
      label:    'Flowers Forever Subscription',
      total:    planData.price,
      recurring: true,
    });

    // Only show the button when the browser/device supports Apple Pay
    applePay.ready(function () {
      applePayContainer.style.display = 'block';

      applePayBtn.addEventListener('click', function () {
        // Validate the delivery fields before opening the Apple Pay sheet
        if (!validateDeliveryFields()) {
          scrollToFirstError();
          return;
        }
        applePay.begin();
      });
    });

    // Apple Pay payment sheet completed — Recurly issues a token just like
    // the card flow; we send it to the same backend endpoint.
    applePay.on('token', function (token) {
      syncBillingAddressToRecurly();
      hideMessages();
      setSubmitLoading(true);
      submitSubscriptionToBackend(token.id);
    });

    applePay.on('error', function (err) {
      console.error('Apple Pay error:', err);
      showError(err.message || 'Apple Pay could not be completed. Please try paying with a card.');
    });
  }

  function getFieldError(field) {
    const messages = {
      number: 'Please enter a valid card number.',
      month:  'Please enter a valid expiry month.',
      year:   'Please enter a valid expiry year.',
      cvv:    'Please enter your CVV.',
    };
    return messages[field] || 'Invalid field.';
  }

  /* ----------------------------------------
     3. FORM VALIDATION
  ---------------------------------------- */
  function validateDeliveryFields() {
    let valid = true;
    const fields = [
      { id: 'first-name',  errorId: 'first-name-error',  label: 'First name' },
      { id: 'last-name',   errorId: 'last-name-error',   label: 'Last name' },
      { id: 'email',       errorId: 'email-error',       label: 'Email address' },
      { id: 'address1',    errorId: 'address1-error',    label: 'Street address' },
      { id: 'city',        errorId: 'city-error',        label: 'City' },
      { id: 'state',       errorId: 'state-error',       label: 'State' },
      { id: 'zip',         errorId: 'zip-error',         label: 'ZIP code' },
    ];

    fields.forEach(({ id, errorId, label }) => {
      const input = el(id);
      const errorSpan = el(errorId);
      if (!input) return;

      const value = input.value.trim();
      let error = '';

      if (!value) {
        error = `${label} is required.`;
      } else if (id === 'email' && !isValidEmail(value)) {
        error = 'Please enter a valid email address.';
      } else if (id === 'zip' && !/^\d{5}$/.test(value)) {
        error = 'Please enter a valid 5-digit ZIP code.';
      }

      if (error) {
        valid = false;
        if (errorSpan) errorSpan.textContent = error;
        input.classList.add('input-error');
      } else {
        if (errorSpan) errorSpan.textContent = '';
        input.classList.remove('input-error');
      }
    });

    return valid;
  }

  function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

  /* ----------------------------------------
     4. BILLING ADDRESS SYNC
  ---------------------------------------- */
  const billingSameCheckbox = el('billing-same-as-delivery');
  const billingAddressFields = el('billing-address-fields');

  if (billingSameCheckbox) {
    billingSameCheckbox.addEventListener('change', () => {
      billingAddressFields.style.display = billingSameCheckbox.checked ? 'none' : 'block';
    });
  }

  function syncBillingAddressToRecurly() {
    if (billingSameCheckbox && billingSameCheckbox.checked) {
      // Copy delivery address into hidden Recurly fields
      const address1El = el('billing-address1');
      const cityEl     = el('billing-city');
      const stateEl    = el('billing-state');
      const zipEl      = el('billing-zip');

      if (address1El) address1El.value = (el('address1') || {}).value || '';
      if (cityEl)     cityEl.value     = (el('city')     || {}).value || '';
      if (stateEl)    stateEl.value    = (el('state')    || {}).value || '';
      if (zipEl)      zipEl.value      = (el('zip')      || {}).value || '';
    } else {
      const address1El = el('billing-address1');
      const cityEl     = el('billing-city');
      const stateEl    = el('billing-state');
      const zipEl      = el('billing-zip');

      if (address1El) address1El.value = (el('billing-street')    || {}).value || '';
      if (cityEl)     cityEl.value     = (el('billing-city-input') || {}).value || '';
      if (stateEl)    stateEl.value    = (el('billing-state-input')|| {}).value || '';
      if (zipEl)      zipEl.value      = (el('billing-zip-input')  || {}).value || '';
    }
  }

  /* ----------------------------------------
     5. COUPON CODE
  ---------------------------------------- */
  const VALID_COUPONS = {
    'FOREVER20': { discount: 0.20, label: '20% off your first box' },
    'WELCOME10': { discount: 0.10, label: '10% off your first box' },
    'BLOOM15':   { discount: 0.15, label: '15% off your first box' },
  };

  let appliedCoupon = null;

  const applyBtn     = el('apply-coupon');
  const couponInput  = el('coupon-code');
  const couponSuccess = el('coupon-success');
  const couponError   = el('coupon-error');

  if (applyBtn) {
    applyBtn.addEventListener('click', () => {
      const code = (couponInput.value || '').trim().toUpperCase();
      if (!code) return;

      const coupon = VALID_COUPONS[code];
      if (coupon) {
        appliedCoupon = { code, ...coupon };
        couponSuccess.textContent = `✓ Code applied! ${coupon.label}.`;
        couponSuccess.style.display = 'block';
        couponError.style.display   = 'none';
        updatePriceSummary();
      } else {
        couponError.style.display   = 'block';
        couponSuccess.style.display = 'none';
        appliedCoupon = null;
        updatePriceSummary();
      }
    });
  }

  function updatePriceSummary() {
    const basePrice  = parseFloat(planData.price);
    const discountRow = el('summary-discount-row');
    const discountEl  = el('summary-discount');
    const totalEl     = el('summary-total');

    if (appliedCoupon) {
      const discountAmt = (basePrice * appliedCoupon.discount).toFixed(2);
      const totalAmt    = (basePrice - parseFloat(discountAmt)).toFixed(2);

      discountEl.textContent = '-$' + discountAmt;
      totalEl.textContent    = '$' + totalAmt;
      if (discountRow) discountRow.style.display = '';
    } else {
      totalEl.textContent = '$' + basePrice.toFixed(2);
      if (discountRow) discountRow.style.display = 'none';
    }
  }

  /* ----------------------------------------
     6. START DATE TOGGLE
  ---------------------------------------- */
  const startDateRadios = document.querySelectorAll('input[name="start_date"]');
  const specificDateInput = el('specific-date');

  startDateRadios.forEach(radio => {
    radio.addEventListener('change', () => {
      if (specificDateInput) {
        specificDateInput.style.display = radio.value === 'specific' ? 'block' : 'none';
      }
    });
  });

  // Set min date to today
  if (specificDateInput) {
    const today = new Date().toISOString().split('T')[0];
    specificDateInput.min = today;
    specificDateInput.value = today;
  }

  /* ----------------------------------------
     6b. IBAN AUTO-FORMAT
     Formats IBAN input as groups of 4 chars (e.g. DE89 3704 0044...)
  ---------------------------------------- */
  const ibanInput = el('sepa-iban');
  if (ibanInput) {
    ibanInput.addEventListener('input', function () {
      let val = ibanInput.value.replace(/\s+/g, '').toUpperCase();
      // Insert a space every 4 characters
      val = val.replace(/(.{4})/g, '$1 ').trim();
      ibanInput.value = val;
    });
  }

  /* ----------------------------------------
     7. FORM SUBMISSION
  ---------------------------------------- */
  const form      = el('subscription-form');
  const submitBtn = el('submit-btn');

  if (form) {
    form.addEventListener('submit', async function (e) {
      e.preventDefault();

      // Validate delivery fields first
      if (!validateDeliveryFields()) {
        scrollToFirstError();
        return;
      }

      // Sync billing address
      syncBillingAddressToRecurly();

      setSubmitLoading(true);
      hideMessages();

      if (typeof recurly === 'undefined') {
        // Demo mode — no Recurly.js loaded, call backend with null token
        submitSubscriptionToBackend('demo-token');
        return;
      }

      const activeTab = window._activePayTab || 'card';

      if (activeTab === 'card') {
        // ── Credit card: Recurly hosted fields token ──
        recurly.token(form, function (err, token) {
          if (err) {
            setSubmitLoading(false);
            showError(err.message || 'Payment processing failed. Please check your card details.');
            return;
          }
          submitSubscriptionToBackend(token.id);
        });

      } else if (activeTab === 'ach' || activeTab === 'sepa') {
        // ── Bank account: validate fields then tokenize ──
        if (!validateBankFields(activeTab)) {
          setSubmitLoading(false);
          showError('Please fill in all required bank account fields.');
          return;
        }
        tokenizeBankAccount(activeTab, function (err, token) {
          if (err) {
            setSubmitLoading(false);
            showError(err.message || 'Bank account verification failed. Please check your details.');
            return;
          }
          submitSubscriptionToBackend(token.id);
        });
      }
    });
  }

  // Backend API base URL — update if your Flask server runs elsewhere.
  const API_BASE = ''; // relative — works on Vercel and localhost alike

  function submitSubscriptionToBackend(recurlyToken) {
    const formData = collectFormData(recurlyToken);

    fetch(`${API_BASE}/api/subscribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData),
    })
    .then(r => r.json().then(data => ({ ok: r.ok, data })))
    .then(({ ok, data }) => {
      if (ok && data.success) {
        handleSuccess(data);
      } else {
        showError(data.message || 'Subscription failed. Please try again.');
      }
    })
    .catch(() => showError('Network error. Please check your connection and try again.'))
    .finally(() => setSubmitLoading(false));
  }

  function handleSuccess(data) {
    // Persist subscription info for the confirmation page
    sessionStorage.setItem('confirmedSubscription', JSON.stringify({
      subscription_id: data.subscription_id,
      account_code:    data.account_code,
      plan:            planData,
    }));

    const successEl = el('success-message');
    if (successEl) {
      successEl.style.display = 'flex';
      successEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    sessionStorage.removeItem('selectedPlan');

    setTimeout(() => {
      window.location.href = 'pages/confirmation.html';
    }, 2500);
  }

  function collectFormData(recurlyToken) {
    return {
      recurly_token:    recurlyToken,
      plan_code:        planData.code,
      first_name:       (el('first-name')  || {}).value || '',
      last_name:        (el('last-name')   || {}).value || '',
      email:            (el('email')       || {}).value || '',
      phone:            (el('phone')       || {}).value || '',
      address: {
        address1: (el('address1') || {}).value || '',
        address2: (el('address2') || {}).value || '',
        city:     (el('city')    || {}).value || '',
        state:    (el('state')   || {}).value || '',
        zip:      (el('zip')     || {}).value || '',
        country:  'US',
      },
      delivery_notes:  (el('delivery-notes') || {}).value || '',
      coupon_code:     appliedCoupon ? appliedCoupon.code : null,
      start_date:      getStartDate(),
      occasion:        (el('occasion') || {}).value || '',
      color_prefs:     getColorPrefs(),
    };
  }

  function getStartDate() {
    const asap = document.querySelector('input[name="start_date"][value="asap"]');
    if (asap && asap.checked) return 'asap';
    return (el('specific-date') || {}).value || 'asap';
  }

  function getColorPrefs() {
    const checkboxes = document.querySelectorAll('input[name="colors"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
  }

  /* ----------------------------------------
     8. UI HELPERS
  ---------------------------------------- */
  function setSubmitLoading(loading) {
    if (!submitBtn) return;
    const textEl    = submitBtn.querySelector('.submit-text');
    const loadingEl = submitBtn.querySelector('.submit-loading');
    submitBtn.disabled = loading;
    if (textEl)    textEl.style.display    = loading ? 'none' : '';
    if (loadingEl) loadingEl.style.display = loading ? 'flex' : 'none';
  }

  function showError(message) {
    const errorEl   = el('error-message');
    const errorText = el('error-text');
    if (errorEl) errorEl.style.display = 'flex';
    if (errorText) errorText.textContent = message;
    errorEl && errorEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function hideMessages() {
    const success = el('success-message');
    const error   = el('error-message');
    if (success) success.style.display = 'none';
    if (error)   error.style.display   = 'none';
  }

  function simulateSuccess() {
    const successEl = el('success-message');
    if (successEl) {
      successEl.style.display = 'flex';
      successEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    // Clear session data
    sessionStorage.removeItem('selectedPlan');

    // Redirect to confirmation after delay
    setTimeout(() => {
      window.location.href = 'pages/confirmation.html';
    }, 2500);
  }

  function scrollToFirstError() {
    const errorEl = document.querySelector('.field-error:not(:empty), .input-error');
    if (errorEl) {
      errorEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }

  /* ----------------------------------------
     9. DEV NOTICE (no Recurly key configured)
  ---------------------------------------- */
  function showDevNotice() {
    const notice = document.createElement('div');
    notice.className = 'dev-notice';
    notice.innerHTML = `
      <strong>🔧 Developer Mode</strong>
      <p>Recurly.js is not configured. To enable live payments:</p>
      <ol>
        <li>Sign up for a <a href="https://recurly.com" target="_blank">Recurly account</a></li>
        <li>Get your <strong>Public API Key</strong> from the Recurly Admin Console</li>
        <li>Replace <code>YOUR_RECURLY_PUBLIC_KEY</code> in <code>js/checkout.js</code></li>
        <li>Set up a subscription plan in Recurly matching your plan codes</li>
        <li>Build a backend endpoint to create Recurly subscriptions</li>
      </ol>
      <p>The form will simulate a successful subscription in demo mode.</p>
    `;
    const formEl = document.getElementById('subscription-form');
    if (formEl) formEl.insertBefore(notice, formEl.firstChild);
  }

})();
