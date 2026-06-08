import { NextRequest, NextResponse } from 'next/server'

// POST /api/cashapp/create-payment
// Creates a Cash App Pay payment via Square API
// Cash App Pay is available through Square's payment ecosystem
export async function POST(req: NextRequest) {
  try {
    const { planId, userId } = await req.json()

    const plans: Record<string, { amount: number; name: string }> = {
      analyst: { amount: 99900, name: 'Analyst Plan — Monthly' },       // Square uses cents
      fund: { amount: 299900, name: 'Fund Plan — Monthly' },
      enterprise: { amount: 0, name: 'Enterprise Plan — Custom' },
    }

    const plan = plans[planId]
    if (!plan) {
      return NextResponse.json({ error: 'Invalid plan' }, { status: 400 })
    }

    if (planId === 'enterprise') {
      return NextResponse.json({ redirect: '/contact' })
    }

    const accessToken = process.env.SQUARE_ACCESS_TOKEN!
    const squareBase = process.env.SQUARE_ENVIRONMENT === 'production'
      ? 'https://connect.squareup.com'
      : 'https://connect.squareupsandbox.com'

    // Create a Square payment with Cash App Pay as the source
    // Step 1: Create a payment link that includes Cash App Pay
    const paymentLinkRes = await fetch(`${squareBase}/v2/online-checkout/payment-links`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Square-Version': '2025-06-18',
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        idempotency_key: `cashapp-${planId}-${userId}-${Date.now()}`,
        quick_pay: {
          name: plan.name,
          price_money: {
            amount: plan.amount,
            currency: 'USD',
          },
          location_id: process.env.SQUARE_LOCATION_ID!,
        },
        payment_options: {
          autocomplete: true,
          accepted_payment_methods: {
            cash_app_pay: true,
            square_pay: true,
            apple_pay: true,
            google_pay: true,
          },
        },
        pre_populate_data: {
          buyer_email: undefined, // populated from user profile
        },
        checkout_options: {
          allow_tipping: false,
          redirect_url: `${process.env.NEXT_PUBLIC_APP_URL}/pricing?cashapp=success&plan=${planId}`,
          custom_fields: [
            {
              title: 'Account ID',
              value: userId,
            },
          ],
        },
      }),
    })

    const paymentLink = await paymentLinkRes.json()

    if (paymentLink.errors) {
      console.error('Square payment link error:', paymentLink.errors)
      return NextResponse.json({ error: 'Cash App payment creation failed' }, { status: 500 })
    }

    const checkoutUrl = paymentLink.payment_link?.url
    const paymentLinkId = paymentLink.payment_link?.id

    return NextResponse.json({
      paymentLinkId,
      checkoutUrl,
      message: 'Cash App Pay checkout link created.',
    })
  } catch (error: any) {
    console.error('Cash App / Square payment error:', error.message)
    return NextResponse.json({ error: 'Failed to create Cash App payment' }, { status: 500 })
  }
}
