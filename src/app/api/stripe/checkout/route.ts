import { NextRequest, NextResponse } from 'next/server'

// POST /api/stripe/checkout
// Creates a Stripe Checkout Session for subscription payment
// Supports: Card, Apple Pay, Google Pay, ACH Direct Debit, Wire, Link
export async function POST(req: NextRequest) {
  try {
    const { planId, userId, email } = await req.json()

    const plans: Record<string, { priceId: string; name: string }> = {
      analyst: { priceId: process.env.STRIPE_ANALYST_PRICE_ID!, name: 'Analyst Plan — Monthly' },
      fund: { priceId: process.env.STRIPE_FUND_PRICE_ID!, name: 'Fund Plan — Monthly' },
      enterprise: { priceId: '', name: 'Enterprise Plan — Custom' },
    }

    const plan = plans[planId]
    if (!plan) {
      return NextResponse.json({ error: 'Invalid plan' }, { status: 400 })
    }

    if (planId === 'enterprise') {
      return NextResponse.json({ redirect: '/contact' })
    }

    // Create Stripe Checkout Session
    const sessionRes = await fetch('https://api.stripe.com/v1/checkout/sessions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        Authorization: `Bearer ${process.env.STRIPE_SECRET_KEY!}`,
      },
      body: new URLSearchParams({
        'mode': 'subscription',
        'customer_email': email || '',
        'client_reference_id': userId,
        'payment_method_types[0]': 'card',
        'payment_method_types[1]': 'link',
        'payment_method_types[2]': 'ach_debit',
        'line_items[0][price]': plan.priceId,
        'line_items[0][quantity]': '1',
        'subscription_data[trial_period_days]': '7',
        'subscription_data[metadata][plan]': planId,
        'subscription_data[metadata][user_id]': userId,
        'success_url': `${process.env.NEXT_PUBLIC_APP_URL}/pricing?stripe=success&plan=${planId}&session_id={CHECKOUT_SESSION_ID}`,
        'cancel_url': `${process.env.NEXT_PUBLIC_APP_URL}/pricing?stripe=cancelled`,
        'allow_promotion_codes': 'true',
        'billing_address_collection': 'required',
        'tax_id_collection[enabled]': 'true',
        'automatic_tax[enabled]': 'true',
        'payment_intent_data[metadata][platform]': 'sahjony-capital',
        'metadata[plan]': planId,
        'metadata[user_id]': userId,
      }),
    })

    const session = await sessionRes.json()

    if (session.error) {
      console.error('Stripe checkout error:', session.error)
      return NextResponse.json({ error: session.error.message }, { status: 500 })
    }

    return NextResponse.json({
      sessionId: session.id,
      url: session.url,
      message: 'Stripe Checkout session created.',
    })
  } catch (error: any) {
    console.error('Stripe checkout error:', error.message)
    return NextResponse.json({ error: 'Failed to create Stripe checkout' }, { status: 500 })
  }
}
