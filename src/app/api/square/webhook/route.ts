import { NextRequest, NextResponse } from 'next/server'

// POST /api/square/webhook
// Handles Square webhooks for payment confirmation (Cash App Pay, Square Pay, card payments)
export async function POST(req: NextRequest) {
  try {
    const body = await req.text()
    const signature = req.headers.get('X-Square-Signature') || ''
    
    // TODO: Verify webhook signature using SQUARE_WEBHOOK_SIGNATURE_KEY
    // import crypto from 'crypto'
    // const hmac = crypto.createHmac('sha256', process.env.SQUARE_WEBHOOK_SIGNATURE_KEY!)
    // hmac.update(body)
    // const expectedSig = hmac.digest('base64')
    // if (signature !== expectedSig) return NextResponse.json({ error: 'Invalid signature' }, { status: 401 })

    const event = JSON.parse(body)

    switch (event.type) {
      case 'payment.updated': {
        const payment = event.data.object.payment
        if (payment.status === 'COMPLETED') {
          const orderId = payment.order_id
          const amount = payment.amount_money?.amount
          const sourceType = payment.source_type // CASH_APP_PAY, SQUARE_PAY, CARD, etc.

          console.log(`✅ Payment completed: ${payment.id} — $${(amount / 100).toFixed(2)} via ${sourceType}`)

          // TODO: Update Supabase
          // const supabase = createClient()
          // await supabase.from('subscriptions').upsert({
          //   user_id: extractUserIdFromOrder(orderId),
          //   plan: mapAmountToPlan(amount),
          //   square_payment_id: payment.id,
          //   payment_source: sourceType,
          //   status: 'active',
          // })
        }
        break
      }

      case 'subscription.created': {
        const subscription = event.data.object.subscription
        console.log(`🔄 Subscription created: ${subscription.id}`)
        // TODO: Record subscription in Supabase
        break
      }

      case 'subscription.stopped': {
        const subscription = event.data.object.subscription
        console.log(`⏹ Subscription stopped: ${subscription.id}`)
        // TODO: Deactivate subscription in Supabase
        break
      }

      default:
        console.log(`ℹ️ Unhandled Square event: ${event.type}`)
    }

    return NextResponse.json({ received: true })
  } catch (error: any) {
    console.error('Square webhook error:', error.message)
    return NextResponse.json({ error: 'Webhook processing failed' }, { status: 500 })
  }
}
