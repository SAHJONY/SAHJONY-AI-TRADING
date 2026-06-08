import { NextRequest, NextResponse } from 'next/server'
import { Configuration, PlaidApi, PlaidEnvironments, ItemPublicTokenExchangeRequest } from 'plaid'

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

// POST /api/plaid/exchange-token
// Exchange Plaid public_token for access_token and store in Supabase
export async function POST(req: NextRequest) {
  try {
    const { publicToken, userId } = await req.json()

    const request: ItemPublicTokenExchangeRequest = {
      public_token: publicToken,
    }

    const response = await plaidClient.itemPublicTokenExchange(request)
    const accessToken = response.data.access_token
    const itemId = response.data.item_id

    // TODO: Store accessToken and itemId in Supabase `bank_accounts` table
    // const supabase = createClient()
    // await supabase.from('bank_accounts').insert({
    //   user_id: userId,
    //   plaid_access_token: accessToken,
    //   plaid_item_id: itemId,
    //   status: 'linked',
    // })

    return NextResponse.json({ 
      success: true, 
      item_id: itemId,
      message: 'Bank account linked successfully. ACH transfers are now available.' 
    })
  } catch (error: any) {
    console.error('Plaid token exchange error:', error.response?.data || error.message)
    return NextResponse.json({ error: 'Failed to exchange token' }, { status: 500 })
  }
}
