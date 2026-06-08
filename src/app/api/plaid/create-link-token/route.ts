import { NextRequest, NextResponse } from 'next/server'
import { Configuration, PlaidApi, PlaidEnvironments, Products, CountryCode } from 'plaid'

const config = new Configuration({
  basePath: PlaidEnvironments.sandbox,
  baseOptions: {
    headers: {
      'PLAID-CLIENT-ID': process.env.PLAID_CLIENT_ID!,
      'PLAID-SECRET': process.env.PLAID_SECRET!,
    },
  },
})

const plaidClient = new PlaidApi(config)

// POST /api/plaid/create-link-token
export async function POST(req: NextRequest) {
  try {
    const { userId } = await req.json()

    const request = {
      user: { client_user_id: userId },
      client_name: 'Sahjony Capital',
      products: [Products.Auth, Products.Transactions],
      country_codes: [CountryCode.Us],
      language: 'en',
      webhook: process.env.PLAID_WEBHOOK_URL,
    }

    const response = await plaidClient.linkTokenCreate(request)

    return NextResponse.json({ link_token: response.data.link_token })
  } catch (error: any) {
    console.error('Plaid link token error:', error.response?.data || error.message)
    return NextResponse.json({ error: 'Failed to create link token' }, { status: 500 })
  }
}
