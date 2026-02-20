# Flowers Forever — Recurly Integration Setup Guide

## Overview

This site uses **Recurly.js v4** for secure, PCI-compliant subscription billing. Recurly.js
renders hosted payment fields (card number, expiry, CVV) in iframes directly on the checkout
page so that raw card data never touches your server.

---

## 1. Create a Recurly Account

1. Go to [https://recurly.com](https://recurly.com) and sign up for an account
2. Complete your business verification
3. In the **Recurly Admin Console**, navigate to **Integrations → API Credentials**
4. Copy your **Public API Key** (starts with `ewr1-...`)

---

## 2. Configure the Public Key

Open `js/checkout.js` and replace the placeholder:

```js
const RECURLY_PUBLIC_KEY = 'YOUR_RECURLY_PUBLIC_KEY';
// Replace with:
const RECURLY_PUBLIC_KEY = 'ewr1-your-actual-key-here';
```

---

## 3. Create Subscription Plans in Recurly

In the Recurly Admin Console, go to **Plans** and create plans matching these codes:

| Plan Name            | Plan Code          | Price   | Interval |
|----------------------|--------------------|---------|----------|
| Classic Bouquet      | classic-monthly    | $49.99  | Monthly  |
| Premium Bouquet      | premium-monthly    | $74.99  | Monthly  |
| Deluxe Bouquet       | deluxe-monthly     | $99.99  | Monthly  |
| Bi-Weekly Blooms     | biweekly-delivery  | $64.99  | Every 2 weeks (use monthly ÷ 2 billing) |
| Weekly Fresh         | weekly-delivery    | $44.99  | Weekly   |
| Rose Garden          | roses-monthly      | $69.99  | Monthly  |
| Tropical Paradise    | tropical-monthly   | $84.99  | Monthly  |
| Pet-Safe Blooms      | petsafe-monthly    | $59.99  | Monthly  |
| Plant of the Month   | plants-monthly     | $54.99  | Monthly  |

---

## 4. Build a Backend API Endpoint

Your server needs an endpoint (e.g., `POST /api/subscribe`) that:

1. **Receives** the Recurly billing token + customer info from the frontend
2. **Creates** a Recurly Account using the Recurly REST API
3. **Creates** a Recurly Subscription using the account, plan code, and token

### Example (Node.js / Express)

```js
const recurly = require('recurly'); // npm install recurly

const client = new recurly.Client('your-private-api-key');

app.post('/api/subscribe', async (req, res) => {
  const { recurly_token, plan_code, first_name, last_name, email, address, coupon_code } = req.body;

  try {
    // Create subscription request
    const subscriptionCreate = {
      planCode: plan_code,
      currency: 'USD',
      account: {
        code: `account-${Date.now()}`,  // or use email as code
        firstName: first_name,
        lastName: last_name,
        email: email,
        address: {
          street1: address.address1,
          street2: address.address2,
          city: address.city,
          region: address.state,
          postalCode: address.zip,
          country: 'US',
        },
        billingInfo: {
          tokenId: recurly_token,  // The Recurly.js token
        },
      },
      ...(coupon_code && { couponCodes: [coupon_code] }),
    };

    const subscription = await client.createSubscription(subscriptionCreate);

    res.json({
      success: true,
      subscription_id: subscription.id,
      account_code: subscription.account.code,
    });
  } catch (err) {
    console.error('Recurly error:', err);
    res.status(400).json({
      success: false,
      message: err.message || 'Subscription creation failed',
    });
  }
});
```

### Example (Python / Flask)

```python
import recurly
from flask import Flask, request, jsonify

client = recurly.Client('your-private-api-key')
app = Flask(__name__)

@app.route('/api/subscribe', methods=['POST'])
def subscribe():
    data = request.json

    try:
        subscription_create = recurly.SubscriptionCreate(
            plan_code=data['plan_code'],
            currency='USD',
            account=recurly.AccountCreate(
                code=f"account-{data['email']}",
                first_name=data['first_name'],
                last_name=data['last_name'],
                email=data['email'],
                billing_info=recurly.BillingInfoCreate(
                    token_id=data['recurly_token']
                )
            )
        )
        subscription = client.create_subscription(subscription_create)
        return jsonify({'success': True, 'subscription_id': subscription.id})

    except recurly.errors.ValidationError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
```

---

## 5. Wire Up the Frontend

In `js/checkout.js`, update `submitSubscriptionToBackend()` to call your real endpoint:

```js
function submitSubscriptionToBackend(recurlyToken) {
  const formData = collectFormData(recurlyToken);

  fetch('/api/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(formData),
  })
  .then(r => r.json())
  .then(data => {
    if (data.success) {
      simulateSuccess(); // rename to handleSuccess
    } else {
      showError(data.message || 'Subscription failed. Please try again.');
    }
  })
  .catch(() => showError('Network error. Please try again.'))
  .finally(() => setSubmitLoading(false));
}
```

---

## 6. Recurly Customer Portal

Enable the self-service portal so subscribers can manage their own subscriptions:

1. In Recurly Admin Console → **Configuration → Customer Portal**
2. Enable and configure the portal
3. Update `pages/account.html` with the actual portal URL

---

## 7. Coupon Codes

To create the demo coupons (`FOREVER20`, `WELCOME10`, `BLOOM15`) in Recurly:

1. Go to **Coupons** in the Recurly Admin Console
2. Create coupons matching those codes with the appropriate discount percentages
3. Set them to apply to the first invoice only

---

## 8. Webhooks (Optional but Recommended)

Set up Recurly webhooks to handle subscription lifecycle events:

- `new_subscription_notification` — send welcome email
- `updated_subscription_notification` — sync plan changes
- `canceled_subscription_notification` — send cancellation confirmation
- `billing_info_updated_notification` — confirm payment update
- `failed_payment_notification` — send payment retry email

Configure your webhook endpoint URL in Recurly Admin Console → **Integrations → Webhooks**.

---

## Environment Variables

```env
RECURLY_PRIVATE_API_KEY=your-private-api-key
RECURLY_PUBLIC_KEY=ewr1-your-public-key
```

Never commit API keys to version control.

---

## File Structure

```
FlowersForever/
├── index.html              # Main homepage
├── checkout.html           # Recurly.js checkout form
├── styles/
│   ├── main.css            # Site-wide styles
│   └── checkout.css        # Checkout-specific styles
├── js/
│   ├── app.js              # Homepage interactions
│   └── checkout.js         # Recurly.js integration
└── pages/
    ├── account.html        # Subscription management
    ├── confirmation.html   # Post-checkout confirmation
    ├── faq.html            # FAQ page
    └── gift.html           # Gift subscriptions
```
