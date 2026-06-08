import { NextRequest, NextResponse } from 'next/server'

// POST /api/stripe/webhook
// Handles Stripe webhooks: subscription created, payment succeeded, payment failed, cancelled
export async function POST(req: NextRequest) {
  try {
    const body = await req.text()
    const sig = req.headers.get('stripe-signature') || ''

    // TODO: Verify webhook signature with stripe library
    // import Stripe from 'stripe'
    // const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!)
    // const event = stripe.webhooks.constructEvent(body, sig, process.env.STRIPE_WEBHOOK_SECRET!)
    
    const event = JSON.parse(body)

    switch (event.type) {
      case 'checkout.session.completed': {
        const session = event.data.object
        const userId = session.client_reference_id
        const plan = session.metadata?.plan
        const customerId = session.customer

        console.log(`✅ Stripe checkout completed: user=${userId} plan=${plan} customer=${customerId}`)

        // TODO: Update Supabase
        // await supabase.from('subscriptions').upsert({
        //   user_id: userId,
        //   plan,
        //   stripe_customer_id: customerId,
        //   stripe_subscription_id: session.subscription,
        //   status: 'active',
        //   current_period_start: new Date().toISOString(),
        // })
        break
      }

      case 'customer.subscription.updated': {
        const subscription = event.data.object
        console.log(`🔄 Stripe subscription updated: ${subscription.id} status=${subscription.status}`)
        // TODO: Sync status in Supabase
        break
      }

      case 'customer.subscription.deleted': {
        const subscription = event.data.object
        console.log(`⏹ Stripe subscription cancelled: ${subscription.id}`)
        // TODO: Deactivate in Supabase
        // await supabase.from('subscriptions').update({ status: 'cancelled' }).eq('stripe_subscription_id', subscription.id)
        break
      }

      case 'invoice.payment_succeeded': {
        const invoice = event.data.object
        console.log(`💰 Stripe invoice paid: ${invoice.id} amount=$${(invoice.amount_paid / 100).toFixed(2)}`)
        // TODO: Record payment, extend subscription period
        break
      }

      case 'invoice.payment_failed': {
        const invoice = event.data.object
        console.log(`❌ Stripe invoice payment failed: ${invoice.id}`)
        // TODO: Mark subscription as past_due, notify user
        // await supabase.from('subscriptions').update({ status: 'past_due' }).eq('stripe_customer_id', invoice.customer)
        break
      }

      case 'customer.subscription.trial_will_end': {
        const subscription = event.data.object
        console.log(`⏰ Stripe trial ending soon: ${subscription.id}`)
        // TODO: Send reminder email
        break
      }

      default:
        console.log(`ℹ️ Unhandled Stripe event: ${event.type}`)
    }

    return NextResponse.json({ received: true })
  } catch (error: any) {
    console.error('Stripe webhook error:', error.message)
    return NextResponse.json({ error: 'Webhook processing failed' }, { status: 500 })
  }
}
