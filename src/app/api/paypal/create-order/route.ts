import { NextRequest, NextResponse } from 'next/server'

// POST /api/paypal/create-order
// Creates a PayPal order for subscription payment
export async function POST(req: NextRequest) {
  try {
    const { planId, userId } = await req.json()

    const plans: Record<string, { amount: string; name: string }> = {
      analyst: { amount: '999.00', name: 'Analyst Plan — Monthly' },
      fund: { amount: '2999.00', name: 'Fund Plan — Monthly' },
      enterprise: { amount: '0.00', name: 'Enterprise Plan — Custom' },
    }

    const plan = plans[planId]
    if (!plan) {
      return NextResponse.json({ error: 'Invalid plan' }, { status: 400 })
    }

    // Enterprise is custom — redirect to contact
    if (planId === 'enterprise') {
      return NextResponse.json({ redirect: '/contact' })
    }

    const accessToken = await getPayPalAccessToken()

    // Create subscription with 7-day free trial
    const subscriptionRes = await fetch(`${getPayPalBase()}/v1/billing/subscriptions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
        'PayPal-Request-Id': `sahjony-${planId}-${userId}-${Date.now()}`,
      },
      body: JSON.stringify({
        plan_id: planId === 'analyst'
          ? process.env.PAYPAL_ANALYST_PLAN_ID
          : process.env.PAYPAL_FUND_PLAN_ID,
        start_time: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(), // charge after 7-day trial
        subscriber: {
          email_address: undefined, // populated from user profile
        },
        application_context: {
          brand_name: 'Sahjony Capital',
          locale: 'en-US',
          shipping_preference: 'NO_SHIPPING',
          user_action: 'SUBSCRIBE_NOW',
          return_url: `${process.env.NEXT_PUBLIC_APP_URL}/pricing?paypal=success&plan=${planId}`,
          cancel_url: `${process.env.NEXT_PUBLIC_APP_URL}/pricing?paypal=cancelled`,
        },
      }),
    })

    const subscription = await subscriptionRes.json()

    if (subscription.error) {
      console.error('PayPal subscription error:', subscription.error)
      return NextResponse.json({ error: 'PayPal subscription creation failed' }, { status: 500 })
    }

    const approvalLink = subscription.links?.find((l: any) => l.rel === 'approve')?.href

    return NextResponse.json({
      subscriptionId: subscription.id,
      approvalUrl: approvalLink,
    })
  } catch (error: any) {
    console.error('PayPal create-order error:', error.message)
    return NextResponse.json({ error: 'Failed to create PayPal order' }, { status: 500 })
  }
}

// POST /api/paypal/create-order?capture=1
// Captures an approved PayPal order
export async function PUT(req: NextRequest) {
  try {
    const { orderId, userId, planId } = await req.json()

    const accessToken = await getPayPalAccessToken()

    const captureRes = await fetch(`${getPayPalBase()}/v2/checkout/orders/${orderId}/capture`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
      },
    })

    const capture = await captureRes.json()

    if (capture.error) {
      console.error('PayPal capture error:', capture.error)
      return NextResponse.json({ error: 'Payment capture failed' }, { status: 500 })
    }

    // TODO: Update Supabase — set user subscription plan, record payment
    // await supabase.from('subscriptions').upsert({
    //   user_id: userId,
    //   plan: planId,
    //   paypal_order_id: orderId,
    //   status: 'active',
    //   current_period_start: new Date().toISOString(),
    // })

    return NextResponse.json({
      success: true,
      plan: planId,
      captureId: capture.id,
      message: 'Subscription activated successfully.',
    })
  } catch (error: any) {
    console.error('PayPal capture error:', error.message)
    return NextResponse.json({ error: 'Failed to capture payment' }, { status: 500 })
  }
}

async function getPayPalAccessToken(): Promise<string> {
  const auth = Buffer.from(
    `${process.env.PAYPAL_CLIENT_ID}:${process.env.PAYPAL_CLIENT_SECRET}`
  ).toString('base64')

  const tokenRes = await fetch(`${getPayPalBase()}/v1/oauth2/token`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Authorization: `Basic ${auth}`,
    },
    body: 'grant_type=client_credentials',
  })

  const tokenData = await tokenRes.json()
  return tokenData.access_token
}

function getPayPalBase(): string {
  return process.env.PAYPAL_MODE === 'live'
    ? 'https://api-m.paypal.com'
    : 'https://api-m.sandbox.paypal.com'
}
