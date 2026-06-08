// ──────────────────────────────────────────────────────────────
// SAHJONY CAPITAL — GLOBAL MARKETS & LANGUAGES REGISTRY
// Every market worldwide. Every language. 24/7/365.
// Zero app store — share the app directly.
// ──────────────────────────────────────────────────────────────

export interface Market {
  id: string
  name: string
  region: string
  country: string
  countryCode: string
  exchange: string
  exchangeCode: string
  timezone: string
  open: string        // local time
  close: string       // local time
  assetTypes: ('equities' | 'forex' | 'crypto' | 'futures' | 'options' | 'commodities' | 'bonds' | 'etfs' | 'indices' | 'cfds')[]
  currency: string
  isActive: boolean
  is247: boolean       // crypto/forex never close
  icon: string
}

export interface Language {
  code: string
  name: string
  nativeName: string
  isSupported: boolean
  regions: string[]
  direction: 'ltr' | 'rtl'
}

// ═══════════════════════════════════════════════════════════
// ALL WORLDWIDE MARKETS — 24/7/365 COVERAGE
// ═══════════════════════════════════════════════════════════

export const MARKETS: Market[] = [
  // ── NORTH AMERICA ──
  { id: 'm-nyse', name: 'New York Stock Exchange', region: 'North America', country: 'United States', countryCode: 'US', exchange: 'NYSE', exchangeCode: 'NYSE', timezone: 'America/New_York', open: '09:30', close: '16:00', assetTypes: ['equities', 'etfs', 'bonds', 'options', 'indices'], currency: 'USD', isActive: true, is247: false, icon: '🇺🇸' },
  { id: 'm-nasdaq', name: 'NASDAQ', region: 'North America', country: 'United States', countryCode: 'US', exchange: 'NASDAQ', exchangeCode: 'NASDAQ', timezone: 'America/New_York', open: '09:30', close: '16:00', assetTypes: ['equities', 'etfs', 'options', 'indices'], currency: 'USD', isActive: true, is247: false, icon: '🇺🇸' },
  { id: 'm-cboe', name: 'CBOE', region: 'North America', country: 'United States', countryCode: 'US', exchange: 'CBOE', exchangeCode: 'CBOE', timezone: 'America/New_York', open: '09:30', close: '16:00', assetTypes: ['options', 'indices', 'futures'], currency: 'USD', isActive: true, is247: false, icon: '🇺🇸' },
  { id: 'm-cme', name: 'CME Group', region: 'North America', country: 'United States', countryCode: 'US', exchange: 'CME', exchangeCode: 'CME', timezone: 'America/Chicago', open: '17:00', close: '16:00', assetTypes: ['futures', 'options', 'commodities', 'indices'], currency: 'USD', isActive: true, is247: false, icon: '🇺🇸' },
  { id: 'm-tsx', name: 'Toronto Stock Exchange', region: 'North America', country: 'Canada', countryCode: 'CA', exchange: 'TSX', exchangeCode: 'TSX', timezone: 'America/Toronto', open: '09:30', close: '16:00', assetTypes: ['equities', 'etfs', 'indices'], currency: 'CAD', isActive: true, is247: false, icon: '🇨🇦' },
  { id: 'm-mexb', name: 'Mexican Stock Exchange', region: 'North America', country: 'Mexico', countryCode: 'MX', exchange: 'BMV', exchangeCode: 'BMV', timezone: 'America/Mexico_City', open: '08:30', close: '15:00', assetTypes: ['equities', 'etfs', 'bonds', 'indices'], currency: 'MXN', isActive: true, is247: false, icon: '🇲🇽' },

  // ── SOUTH AMERICA ──
  { id: 'm-b3', name: 'B3 – Brasil Bolsa Balcão', region: 'South America', country: 'Brazil', countryCode: 'BR', exchange: 'B3', exchangeCode: 'BVMF', timezone: 'America/Sao_Paulo', open: '10:00', close: '17:00', assetTypes: ['equities', 'futures', 'options', 'etfs', 'indices'], currency: 'BRL', isActive: true, is247: false, icon: '🇧🇷' },
  { id: 'm-bcs', name: 'Bolsa de Santiago', region: 'South America', country: 'Chile', countryCode: 'CL', exchange: 'BSCS', exchangeCode: 'BSCS', timezone: 'America/Santiago', open: '09:30', close: '16:00', assetTypes: ['equities', 'etfs', 'indices'], currency: 'CLP', isActive: true, is247: false, icon: '🇨🇱' },
  { id: 'm-bcba', name: 'Bolsa de Comercio de Buenos Aires', region: 'South America', country: 'Argentina', countryCode: 'AR', exchange: 'BCBA', exchangeCode: 'BCBA', timezone: 'America/Argentina/Buenos_Aires', open: '11:00', close: '17:00', assetTypes: ['equities', 'bonds', 'options', 'indices'], currency: 'ARS', isActive: true, is247: false, icon: '🇦🇷' },
  { id: 'm-bvl', name: 'Bolsa de Valores de Lima', region: 'South America', country: 'Peru', countryCode: 'PE', exchange: 'BVL', exchangeCode: 'BVL', timezone: 'America/Lima', open: '09:00', close: '16:00', assetTypes: ['equities', 'bonds', 'indices'], currency: 'PEN', isActive: true, is247: false, icon: '🇵🇪' },
  { id: 'm-bvc', name: 'Bolsa de Valores de Colombia', region: 'South America', country: 'Colombia', countryCode: 'CO', exchange: 'BVC', exchangeCode: 'BVC', timezone: 'America/Bogota', open: '09:00', close: '15:00', assetTypes: ['equities', 'bonds', 'indices'], currency: 'COP', isActive: true, is247: false, icon: '🇨🇴' },

  // ── EUROPE ──
  { id: 'm-lse', name: 'London Stock Exchange', region: 'Europe', country: 'United Kingdom', countryCode: 'GB', exchange: 'LSE', exchangeCode: 'LSE', timezone: 'Europe/London', open: '08:00', close: '16:30', assetTypes: ['equities', 'etfs', 'bonds', 'indices'], currency: 'GBP', isActive: true, is247: false, icon: '🇬🇧' },
  { id: 'm-xetra', name: 'Frankfurt Stock Exchange (Xetra)', region: 'Europe', country: 'Germany', countryCode: 'DE', exchange: 'Xetra', exchangeCode: 'XETR', timezone: 'Europe/Berlin', open: '09:00', close: '17:30', assetTypes: ['equities', 'etfs', 'bonds', 'indices'], currency: 'EUR', isActive: true, is247: false, icon: '🇩🇪' },
  { id: 'm-euronext', name: 'Euronext Paris', region: 'Europe', country: 'France', countryCode: 'FR', exchange: 'Euronext', exchangeCode: 'EUROPA', timezone: 'Europe/Paris', open: '09:00', close: '17:30', assetTypes: ['equities', 'etfs', 'bonds', 'options', 'indices'], currency: 'EUR', isActive: true, is247: false, icon: '🇫🇷' },
  { id: 'm-euronext-am', name: 'Euronext Amsterdam', region: 'Europe', country: 'Netherlands', countryCode: 'NL', exchange: 'Euronext', exchangeCode: 'EUROAM', timezone: 'Europe/Amsterdam', open: '09:00', close: '17:30', assetTypes: ['equities', 'etfs', 'options', 'indices'], currency: 'EUR', isActive: true, is247: false, icon: '🇳🇱' },
  { id: 'm-euronext-mi', name: 'Borsa Italiana (Euronext Milan)', region: 'Europe', country: 'Italy', countryCode: 'IT', exchange: 'Euronext', exchangeCode: 'EUROMI', timezone: 'Europe/Rome', open: '09:00', close: '17:30', assetTypes: ['equities', 'etfs', 'bonds', 'options', 'indices'], currency: 'EUR', isActive: true, is247: false, icon: '🇮🇹' },
  { id: 'm-euronext-br', name: 'Euronext Brussels', region: 'Europe', country: 'Belgium', countryCode: 'BE', exchange: 'Euronext', exchangeCode: 'EUROBR', timezone: 'Europe/Brussels', open: '09:00', close: '17:30', assetTypes: ['equities', 'bonds', 'indices'], currency: 'EUR', isActive: true, is247: false, icon: '🇧🇪' },
  { id: 'm-euronext-li', name: 'Euronext Lisbon', region: 'Europe', country: 'Portugal', countryCode: 'PT', exchange: 'Euronext', exchangeCode: 'EUROLI', timezone: 'Europe/Lisbon', open: '09:00', close: '17:30', assetTypes: ['equities', 'bonds', 'indices'], currency: 'EUR', isActive: true, is247: false, icon: '🇵🇹' },
  { id: 'm-euronext-dl', name: 'Euronext Dublin', region: 'Europe', country: 'Ireland', countryCode: 'IE', exchange: 'Euronext', exchangeCode: 'EURODL', timezone: 'Europe/Dublin', open: '08:00', close: '16:30', assetTypes: ['equities', 'etfs', 'bonds', 'indices'], currency: 'EUR', isActive: true, is247: false, icon: '🇮🇪' },
  { id: 'm-six', name: 'SIX Swiss Exchange', region: 'Europe', country: 'Switzerland', countryCode: 'CH', exchange: 'SIX', exchangeCode: 'SIX', timezone: 'Europe/Zurich', open: '09:00', close: '17:30', assetTypes: ['equities', 'etfs', 'bonds', 'indices'], currency: 'CHF', isActive: true, is247: false, icon: '🇨🇭' },
  { id: 'm-nasdaq-sto', name: 'Nasdaq Stockholm', region: 'Europe', country: 'Sweden', countryCode: 'SE', exchange: 'Nasdaq Nordic', exchangeCode: 'STO', timezone: 'Europe/Stockholm', open: '09:00', close: '17:30', assetTypes: ['equities', 'etfs', 'indices'], currency: 'SEK', isActive: true, is247: false, icon: '🇸🇪' },
  { id: 'm-nasdaq-hel', name: 'Nasdaq Helsinki', region: 'Europe', country: 'Finland', countryCode: 'FI', exchange: 'Nasdaq Nordic', exchangeCode: 'HEL', timezone: 'Europe/Helsinki', open: '09:00', close: '17:30', assetTypes: ['equities', 'indices'], currency: 'EUR', isActive: true, is247: false, icon: '🇫🇮' },
  { id: 'm-nasdaq-cop', name: 'Nasdaq Copenhagen', region: 'Europe', country: 'Denmark', countryCode: 'DK', exchange: 'Nasdaq Nordic', exchangeCode: 'CPH', timezone: 'Europe/Copenhagen', open: '09:00', close: '17:00', assetTypes: ['equities', 'indices'], currency: 'DKK', isActive: true, is247: false, icon: '🇩🇰' },
  { id: 'm-nasdaq-osl', name: 'Oslo Børs', region: 'Europe', country: 'Norway', countryCode: 'NO', exchange: 'Euronext', exchangeCode: 'OSL', timezone: 'Europe/Oslo', open: '09:00', close: '16:20', assetTypes: ['equities', 'indices'], currency: 'NOK', isActive: true, is247: false, icon: '🇳🇴' },
  { id: 'm-wse', name: 'Warsaw Stock Exchange', region: 'Europe', country: 'Poland', countryCode: 'PL', exchange: 'GPW', exchangeCode: 'WSE', timezone: 'Europe/Warsaw', open: '09:00', close: '17:00', assetTypes: ['equities', 'etfs', 'bonds', 'indices'], currency: 'PLN', isActive: true, is247: false, icon: '🇵🇱' },
  { id: 'm-pra', name: 'Prague Stock Exchange', region: 'Europe', country: 'Czech Republic', countryCode: 'CZ', exchange: 'PSE', exchangeCode: 'PSE', timezone: 'Europe/Prague', open: '09:00', close: '16:20', assetTypes: ['equities', 'indices'], currency: 'CZK', isActive: true, is247: false, icon: '🇨🇿' },
  { id: 'm-bud', name: 'Budapest Stock Exchange', region: 'Europe', country: 'Hungary', countryCode: 'HU', exchange: 'BSE', exchangeCode: 'BUD', timezone: 'Europe/Budapest', open: '09:00', close: '16:30', assetTypes: ['equities', 'indices'], currency: 'HUF', isActive: true, is247: false, icon: '🇭🇺' },
  { id: 'm-bvb', name: 'Bursa de Valori București', region: 'Europe', country: 'Romania', countryCode: 'RO', exchange: 'BVB', exchangeCode: 'BVB', timezone: 'Europe/Bucharest', open: '09:00', close: '16:30', assetTypes: ['equities', 'indices'], currency: 'RON', isActive: true, is247: false, icon: '🇷🇴' },
  { id: 'm-moex', name: 'Moscow Exchange', region: 'Europe', country: 'Russia', countryCode: 'RU', exchange: 'MOEX', exchangeCode: 'MOEX', timezone: 'Europe/Moscow', open: '10:00', close: '18:45', assetTypes: ['equities', 'bonds', 'futures', 'indices'], currency: 'RUB', isActive: true, is247: false, icon: '🇷🇺' },
  { id: 'm-ise', name: 'Istanbul Stock Exchange (BIST)', region: 'Europe', country: 'Turkey', countryCode: 'TR', exchange: 'BIST', exchangeCode: 'BIST', timezone: 'Europe/Istanbul', open: '10:00', close: '18:00', assetTypes: ['equities', 'futures', 'options', 'indices'], currency: 'TRY', isActive: true, is247: false, icon: '🇹🇷' },
  { id: 'm-athex', name: 'Athens Stock Exchange', region: 'Europe', country: 'Greece', countryCode: 'GR', exchange: 'ATHEX', exchangeCode: 'ATHEX', timezone: 'Europe/Athens', open: '10:00', close: '17:30', assetTypes: ['equities', 'bonds', 'indices'], currency: 'EUR', isActive: true, is247: false, icon: '🇬🇷' },
  { id: 'm-zagreb', name: 'Zagreb Stock Exchange', region: 'Europe', country: 'Croatia', countryCode: 'HR', exchange: 'ZSE', exchangeCode: 'ZSE', timezone: 'Europe/Zagreb', open: '09:00', close: '16:00', assetTypes: ['equities', 'bonds'], currency: 'EUR', isActive: true, is247: false, icon: '🇭🇷' },

  // ── ASIA-PACIFIC ──
  { id: 'm-tse', name: 'Tokyo Stock Exchange', region: 'Asia-Pacific', country: 'Japan', countryCode: 'JP', exchange: 'JPX', exchangeCode: 'TYO', timezone: 'Asia/Tokyo', open: '09:00', close: '15:00', assetTypes: ['equities', 'etfs', 'futures', 'options', 'bonds', 'indices'], currency: 'JPY', isActive: true, is247: false, icon: '🇯🇵' },
  { id: 'm-ose', name: 'Osaka Exchange (Derivatives)', region: 'Asia-Pacific', country: 'Japan', countryCode: 'JP', exchange: 'JPX', exchangeCode: 'OSE', timezone: 'Asia/Tokyo', open: '08:45', close: '15:15', assetTypes: ['futures', 'options', 'indices'], currency: 'JPY', isActive: true, is247: false, icon: '🇯🇵' },
  { id: 'm-hkex', name: 'Hong Kong Stock Exchange', region: 'Asia-Pacific', country: 'Hong Kong', countryCode: 'HK', exchange: 'HKEX', exchangeCode: 'HKG', timezone: 'Asia/Hong_Kong', open: '09:30', close: '16:00', assetTypes: ['equities', 'etfs', 'futures', 'options', 'bonds', 'indices'], currency: 'HKD', isActive: true, is247: false, icon: '🇭🇰' },
  { id: 'm-sse', name: 'Shanghai Stock Exchange', region: 'Asia-Pacific', country: 'China', countryCode: 'CN', exchange: 'SSE', exchangeCode: 'SHA', timezone: 'Asia/Shanghai', open: '09:30', close: '15:00', assetTypes: ['equities', 'bonds', 'etfs', 'indices'], currency: 'CNY', isActive: true, is247: false, icon: '🇨🇳' },
  { id: 'm-szse', name: 'Shenzhen Stock Exchange', region: 'Asia-Pacific', country: 'China', countryCode: 'CN', exchange: 'SZSE', exchangeCode: 'SHE', timezone: 'Asia/Shanghai', open: '09:30', close: '15:00', assetTypes: ['equities', 'etfs', 'indices'], currency: 'CNY', isActive: true, is247: false, icon: '🇨🇳' },
  { id: 'm-cffex', name: 'China Financial Futures Exchange', region: 'Asia-Pacific', country: 'China', countryCode: 'CN', exchange: 'CFFEX', exchangeCode: 'CFFEX', timezone: 'Asia/Shanghai', open: '09:15', close: '15:15', assetTypes: ['futures', 'indices'], currency: 'CNY', isActive: true, is247: false, icon: '🇨🇳' },
  { id: 'm-ksse', name: 'Korea Exchange (KRX)', region: 'Asia-Pacific', country: 'South Korea', countryCode: 'KR', exchange: 'KRX', exchangeCode: 'KRX', timezone: 'Asia/Seoul', open: '09:00', close: '15:30', assetTypes: ['equities', 'futures', 'options', 'indices'], currency: 'KRW', isActive: true, is247: false, icon: '🇰🇷' },
  { id: 'm-taiex', name: 'Taiwan Stock Exchange', region: 'Asia-Pacific', country: 'Taiwan', countryCode: 'TW', exchange: 'TWSE', exchangeCode: 'TAI', timezone: 'Asia/Taipei', open: '09:00', close: '13:30', assetTypes: ['equities', 'etfs', 'indices'], currency: 'TWD', isActive: true, is247: false, icon: '🇹🇼' },
  { id: 'm-sgx', name: 'Singapore Exchange', region: 'Asia-Pacific', country: 'Singapore', countryCode: 'SG', exchange: 'SGX', exchangeCode: 'SGX', timezone: 'Asia/Singapore', open: '09:00', close: '17:00', assetTypes: ['equities', 'futures', 'options', 'bonds', 'indices'], currency: 'SGD', isActive: true, is247: false, icon: '🇸🇬' },
  { id: 'm-bse', name: 'Bombay Stock Exchange', region: 'Asia-Pacific', country: 'India', countryCode: 'IN', exchange: 'BSE', exchangeCode: 'BSE', timezone: 'Asia/Kolkata', open: '09:15', close: '15:30', assetTypes: ['equities', 'etfs', 'bonds', 'indices'], currency: 'INR', isActive: true, is247: false, icon: '🇮🇳' },
  { id: 'm-nse', name: 'National Stock Exchange of India', region: 'Asia-Pacific', country: 'India', countryCode: 'IN', exchange: 'NSE', exchangeCode: 'NSE', timezone: 'Asia/Kolkata', open: '09:15', close: '15:30', assetTypes: ['equities', 'futures', 'options', 'etfs', 'indices'], currency: 'INR', isActive: true, is247: false, icon: '🇮🇳' },
  { id: 'm-asx', name: 'Australian Securities Exchange', region: 'Asia-Pacific', country: 'Australia', countryCode: 'AU', exchange: 'ASX', exchangeCode: 'ASX', timezone: 'Australia/Sydney', open: '10:00', close: '16:00', assetTypes: ['equities', 'etfs', 'futures', 'options', 'bonds', 'indices'], currency: 'AUD', isActive: true, is247: false, icon: '🇦🇺' },
  { id: 'm-nzx', name: 'New Zealand Exchange', region: 'Asia-Pacific', country: 'New Zealand', countryCode: 'NZ', exchange: 'NZX', exchangeCode: 'NZX', timezone: 'Pacific/Auckland', open: '10:00', close: '16:45', assetTypes: ['equities', 'etfs', 'bonds', 'indices'], currency: 'NZD', isActive: true, is247: false, icon: '🇳🇿' },
  { id: 'm-idx', name: 'Indonesia Stock Exchange', region: 'Asia-Pacific', country: 'Indonesia', countryCode: 'ID', exchange: 'IDX', exchangeCode: 'IDX', timezone: 'Asia/Jakarta', open: '09:00', close: '15:50', assetTypes: ['equities', 'bonds', 'indices'], currency: 'IDR', isActive: true, is247: false, icon: '🇮🇩' },
  { id: 'm-klse', name: 'Bursa Malaysia', region: 'Asia-Pacific', country: 'Malaysia', countryCode: 'MY', exchange: 'Bursa', exchangeCode: 'KLS', timezone: 'Asia/Kuala_Lumpur', open: '09:00', close: '17:00', assetTypes: ['equities', 'etfs', 'bonds', 'indices'], currency: 'MYR', isActive: true, is247: false, icon: '🇲🇾' },
  { id: 'm-set', name: 'Stock Exchange of Thailand', region: 'Asia-Pacific', country: 'Thailand', countryCode: 'TH', exchange: 'SET', exchangeCode: 'SET', timezone: 'Asia/Bangkok', open: '10:00', close: '16:30', assetTypes: ['equities', 'futures', 'indices'], currency: 'THB', isActive: true, is247: false, icon: '🇹🇭' },
  { id: 'm-pse', name: 'Philippine Stock Exchange', region: 'Asia-Pacific', country: 'Philippines', countryCode: 'PH', exchange: 'PSE', exchangeCode: 'PSE', timezone: 'Asia/Manila', open: '09:30', close: '15:00', assetTypes: ['equities', 'indices'], currency: 'PHP', isActive: true, is247: false, icon: '🇵🇭' },
  { id: 'm-hsx', name: 'Ho Chi Minh Stock Exchange', region: 'Asia-Pacific', country: 'Vietnam', countryCode: 'VN', exchange: 'HOSE', exchangeCode: 'HOSE', timezone: 'Asia/Ho_Chi_Minh', open: '09:00', close: '15:00', assetTypes: ['equities', 'bonds', 'indices'], currency: 'VND', isActive: true, is247: false, icon: '🇻🇳' },
  { id: 'm-twse', name: 'Colombo Stock Exchange', region: 'Asia-Pacific', country: 'Sri Lanka', countryCode: 'LK', exchange: 'CSE', exchangeCode: 'CSE', timezone: 'Asia/Colombo', open: '09:30', close: '14:30', assetTypes: ['equities', 'indices'], currency: 'LKR', isActive: true, is247: false, icon: '🇱🇰' },
  { id: 'm-dse', name: 'Dhaka Stock Exchange', region: 'Asia-Pacific', country: 'Bangladesh', countryCode: 'BD', exchange: 'DSE', exchangeCode: 'DSE', timezone: 'Asia/Dhaka', open: '10:00', close: '14:00', assetTypes: ['equities', 'indices'], currency: 'BDT', isActive: true, is247: false, icon: '🇧🇩' },

  // ── MIDDLE EAST ──
  { id: 'm-tadawul', name: 'Tadawul (Saudi Stock Exchange)', region: 'Middle East', country: 'Saudi Arabia', countryCode: 'SA', exchange: 'Tadawul', exchangeCode: 'TADAWUL', timezone: 'Asia/Riyadh', open: '10:00', close: '15:00', assetTypes: ['equities', 'etfs', 'bonds', 'indices'], currency: 'SAR', isActive: true, is247: false, icon: '🇸🇦' },
  { id: 'm-dfm', name: 'Dubai Financial Market', region: 'Middle East', country: 'UAE', countryCode: 'AE', exchange: 'DFM', exchangeCode: 'DFM', timezone: 'Asia/Dubai', open: '10:00', close: '14:00', assetTypes: ['equities', 'bonds', 'indices'], currency: 'AED', isActive: true, is247: false, icon: '🇦🇪' },
  { id: 'm-adsm', name: 'Abu Dhabi Securities Exchange', region: 'Middle East', country: 'UAE', countryCode: 'AE', exchange: 'ADX', exchangeCode: 'ADX', timezone: 'Asia/Dubai', open: '10:00', close: '14:00', assetTypes: ['equities', 'bonds', 'indices'], currency: 'AED', isActive: true, is247: false, icon: '🇦🇪' },
  { id: 'm-tase', name: 'Tel Aviv Stock Exchange', region: 'Middle East', country: 'Israel', countryCode: 'IL', exchange: 'TASE', exchangeCode: 'TASE', timezone: 'Asia/Jerusalem', open: '09:00', close: '15:30', assetTypes: ['equities', 'etfs', 'bonds', 'indices'], currency: 'ILS', isActive: true, is247: false, icon: '🇮🇱' },
  { id: 'm-bahrain', name: 'Bahrain Bourse', region: 'Middle East', country: 'Bahrain', countryCode: 'BH', exchange: 'BHB', exchangeCode: 'BHB', timezone: 'Asia/Bahrain', open: '09:30', close: '13:30', assetTypes: ['equities', 'bonds', 'indices'], currency: 'BHD', isActive: true, is247: false, icon: '🇧🇭' },
  { id: 'm-kuwait', name: 'Kuwait Stock Exchange', region: 'Middle East', country: 'Kuwait', countryCode: 'KW', exchange: 'Boursa Kuwait', exchangeCode: 'KSE', timezone: 'Asia/Kuwait', open: '09:00', close: '13:30', assetTypes: ['equities', 'indices'], currency: 'KWD', isActive: true, is247: false, icon: '🇰🇼' },
  { id: 'm-msm', name: 'Muscat Securities Market', region: 'Middle East', country: 'Oman', countryCode: 'OM', exchange: 'MSM', exchangeCode: 'MSM', timezone: 'Asia/Muscat', open: '10:00', close: '14:00', assetTypes: ['equities', 'bonds', 'indices'], currency: 'OMR', isActive: true, is247: false, icon: '🇴🇲' },
  { id: 'm-qse', name: 'Qatar Stock Exchange', region: 'Middle East', country: 'Qatar', countryCode: 'QA', exchange: 'QSE', exchangeCode: 'QSE', timezone: 'Asia/Qatar', open: '09:30', close: '13:00', assetTypes: ['equities', 'indices'], currency: 'QAR', isActive: true, is247: false, icon: '🇶🇦' },
  { id: 'm-iran', name: 'Tehran Stock Exchange', region: 'Middle East', country: 'Iran', countryCode: 'IR', exchange: 'TSE', exchangeCode: 'TSE', timezone: 'Asia/Tehran', open: '08:30', close: '12:30', assetTypes: ['equities', 'bonds', 'indices'], currency: 'IRR', isActive: true, is247: false, icon: '🇮🇷' },

  // ── AFRICA ──
  { id: 'm-jse', name: 'Johannesburg Stock Exchange', region: 'Africa', country: 'South Africa', countryCode: 'ZA', exchange: 'JSE', exchangeCode: 'JSE', timezone: 'Africa/Johannesburg', open: '09:00', close: '17:00', assetTypes: ['equities', 'etfs', 'futures', 'options', 'bonds', 'indices'], currency: 'ZAR', isActive: true, is247: false, icon: '🇿🇦' },
  { id: 'm-ngx', name: 'Nigerian Exchange Group', region: 'Africa', country: 'Nigeria', countryCode: 'NG', exchange: 'NGX', exchangeCode: 'NGX', timezone: 'Africa/Lagos', open: '09:30', close: '14:30', assetTypes: ['equities', 'bonds', 'indices'], currency: 'NGN', isActive: true, is247: false, icon: '🇳🇬' },
  { id: 'm-nse-ke', name: 'Nairobi Securities Exchange', region: 'Africa', country: 'Kenya', countryCode: 'KE', exchange: 'NSE', exchangeCode: 'NSEKE', timezone: 'Africa/Nairobi', open: '09:00', close: '15:00', assetTypes: ['equities', 'bonds', 'indices'], currency: 'KES', isActive: true, is247: false, icon: '🇰🇪' },
  { id: 'm-egx', name: 'Egyptian Exchange', region: 'Africa', country: 'Egypt', countryCode: 'EG', exchange: 'EGX', exchangeCode: 'EGX', timezone: 'Africa/Cairo', open: '10:00', close: '14:00', assetTypes: ['equities', 'bonds', 'indices'], currency: 'EGP', isActive: true, is247: false, icon: '🇪🇬' },
  { id: 'm-casablanca', name: 'Casablanca Stock Exchange', region: 'Africa', country: 'Morocco', countryCode: 'MA', exchange: 'BVC', exchangeCode: 'BVCMA', timezone: 'Africa/Casablanca', open: '09:00', close: '17:00', assetTypes: ['equities', 'bonds', 'indices'], currency: 'MAD', isActive: true, is247: false, icon: '🇲🇦' },
  { id: 'm-brvm', name: 'Bourse Régionale des Valeurs Mobilières', region: 'Africa', country: 'West Africa (regional)', countryCode: 'CI', exchange: 'BRVM', exchangeCode: 'BRVM', timezone: 'Africa/Abidjan', open: '09:00', close: '15:00', assetTypes: ['equities', 'bonds', 'indices'], currency: 'XOF', isActive: true, is247: false, icon: '🌍' },
  { id: 'm-dse-tz', name: 'Dar es Salaam Stock Exchange', region: 'Africa', country: 'Tanzania', countryCode: 'TZ', exchange: 'DSE', exchangeCode: 'DSETZ', timezone: 'Africa/Dar_es_Salaam', open: '10:00', close: '14:00', assetTypes: ['equities', 'bonds'], currency: 'TZS', isActive: true, is247: false, icon: '🇹🇿' },
  { id: 'm-gse', name: 'Ghana Stock Exchange', region: 'Africa', country: 'Ghana', countryCode: 'GH', exchange: 'GSE', exchangeCode: 'GSE', timezone: 'Africa/Accra', open: '10:00', close: '15:00', assetTypes: ['equities', 'indices'], currency: 'GHS', isActive: true, is247: false, icon: '🇬🇭' },
  { id: 'm-use', name: 'Uganda Securities Exchange', region: 'Africa', country: 'Uganda', countryCode: 'UG', exchange: 'USE', exchangeCode: 'USE', timezone: 'Africa/Kampala', open: '10:00', close: '14:00', assetTypes: ['equities', 'bonds'], currency: 'UGX', isActive: true, is247: false, icon: '🇺🇬' },
  { id: 'm-mauritius', name: 'Stock Exchange of Mauritius', region: 'Africa', country: 'Mauritius', countryCode: 'MU', exchange: 'SEM', exchangeCode: 'SEM', timezone: 'Indian/Mauritius', open: '09:00', close: '14:30', assetTypes: ['equities', 'etfs', 'indices'], currency: 'MUR', isActive: true, is247: false, icon: '🇲🇺' },

  // ── 24/7/365 MARKETS — Never Close ──
  { id: 'm-crypto', name: 'Global Crypto Market', region: 'Global', country: 'Worldwide', countryCode: 'GL', exchange: 'Decentralized', exchangeCode: 'CRYPTO', timezone: 'UTC', open: '00:00', close: '23:59', assetTypes: ['crypto'], currency: 'USD', isActive: true, is247: true, icon: '₿' },
  { id: 'm-forex', name: 'Global Forex Market', region: 'Global', country: 'Worldwide', countryCode: 'GL', exchange: 'Interbank', exchangeCode: 'FOREX', timezone: 'UTC', open: '00:00', close: '23:59', assetTypes: ['forex'], currency: 'USD', isActive: true, is247: true, icon: '💱' },
  { id: 'm-otc', name: 'OTC / Pink Sheets', region: 'Global', country: 'Worldwide', countryCode: 'GL', exchange: 'OTC Markets', exchangeCode: 'OTC', timezone: 'America/New_York', open: '06:00', close: '20:00', assetTypes: ['equities', 'bonds'], currency: 'USD', isActive: true, is247: false, icon: '🌐' },

  // ── PRE/POST MARKET (Extended Hours) ──
  { id: 'm-pre-us', name: 'US Pre-Market (4:00–9:30 ET)', region: 'North America', country: 'United States', countryCode: 'US', exchange: 'ECN', exchangeCode: 'PREUS', timezone: 'America/New_York', open: '04:00', close: '09:30', assetTypes: ['equities', 'etfs', 'indices'], currency: 'USD', isActive: true, is247: false, icon: '🌙' },
  { id: 'm-post-us', name: 'US After-Hours (16:00–20:00 ET)', region: 'North America', country: 'United States', countryCode: 'US', exchange: 'ECN', exchangeCode: 'POSTUS', timezone: 'America/New_York', open: '16:00', close: '20:00', assetTypes: ['equities', 'etfs', 'indices'], currency: 'USD', isActive: true, is247: false, icon: '🌑' },
]

// ═══════════════════════════════════════════════════════════
// ALL LANGUAGES — FULL GLOBAL COVERAGE
// ═══════════════════════════════════════════════════════════

export const LANGUAGES: Language[] = [
  { code: 'en', name: 'English', nativeName: 'English', isSupported: true, regions: ['US', 'GB', 'AU', 'CA', 'NZ', 'IE', 'SG', 'ZA', 'NG', 'KE', 'GH', 'IN'], direction: 'ltr' },
  { code: 'es', name: 'Spanish', nativeName: 'Español', isSupported: true, regions: ['MX', 'AR', 'CO', 'CL', 'PE', 'ES', 'VE', 'EC', 'GT', 'CU', 'BO', 'DO', 'HN', 'PY', 'SV', 'NI', 'CR', 'PA', 'UY'], direction: 'ltr' },
  { code: 'zh', name: 'Chinese (Simplified)', nativeName: '简体中文', isSupported: true, regions: ['CN', 'SG'], direction: 'ltr' },
  { code: 'zh-TW', name: 'Chinese (Traditional)', nativeName: '繁體中文', isSupported: true, regions: ['TW', 'HK', 'MO'], direction: 'ltr' },
  { code: 'hi', name: 'Hindi', nativeName: 'हिन्दी', isSupported: true, regions: ['IN'], direction: 'ltr' },
  { code: 'ar', name: 'Arabic', nativeName: 'العربية', isSupported: true, regions: ['SA', 'AE', 'KW', 'QA', 'BH', 'OM', 'EG', 'JO', 'LB', 'IQ', 'MA', 'DZ', 'TN', 'LY', 'SD', 'YE'], direction: 'rtl' },
  { code: 'pt', name: 'Portuguese', nativeName: 'Português', isSupported: true, regions: ['BR', 'PT', 'AO', 'MZ', 'GW'], direction: 'ltr' },
  { code: 'fr', name: 'French', nativeName: 'Français', isSupported: true, regions: ['FR', 'BE', 'CH', 'CA', 'CI', 'SN', 'ML', 'BF', 'BJ', 'NE', 'TG', 'GA', 'CM', 'CG', 'CD', 'MG', 'HT', 'MA', 'DZ', 'TN', 'LU'], direction: 'ltr' },
  { code: 'de', name: 'German', nativeName: 'Deutsch', isSupported: true, regions: ['DE', 'AT', 'CH', 'LU', 'LI'], direction: 'ltr' },
  { code: 'ja', name: 'Japanese', nativeName: '日本語', isSupported: true, regions: ['JP'], direction: 'ltr' },
  { code: 'ko', name: 'Korean', nativeName: '한국어', isSupported: true, regions: ['KR'], direction: 'ltr' },
  { code: 'ru', name: 'Russian', nativeName: 'Русский', isSupported: true, regions: ['RU', 'BY', 'KZ', 'UZ', 'UA', 'KG', 'TJ', 'TM', 'MD'], direction: 'ltr' },
  { code: 'it', name: 'Italian', nativeName: 'Italiano', isSupported: true, regions: ['IT', 'CH', 'SM', 'VA'], direction: 'ltr' },
  { code: 'nl', name: 'Dutch', nativeName: 'Nederlands', isSupported: true, regions: ['NL', 'BE', 'SR', 'AW', 'CW'], direction: 'ltr' },
  { code: 'tr', name: 'Turkish', nativeName: 'Türkçe', isSupported: true, regions: ['TR', 'CY'], direction: 'ltr' },
  { code: 'pl', name: 'Polish', nativeName: 'Polski', isSupported: true, regions: ['PL'], direction: 'ltr' },
  { code: 'sv', name: 'Swedish', nativeName: 'Svenska', isSupported: true, regions: ['SE'], direction: 'ltr' },
  { code: 'da', name: 'Danish', nativeName: 'Dansk', isSupported: true, regions: ['DK'], direction: 'ltr' },
  { code: 'fi', name: 'Finnish', nativeName: 'Suomi', isSupported: true, regions: ['FI'], direction: 'ltr' },
  { code: 'nb', name: 'Norwegian', nativeName: 'Norsk', isSupported: true, regions: ['NO'], direction: 'ltr' },
  { code: 'cs', name: 'Czech', nativeName: 'Čeština', isSupported: true, regions: ['CZ'], direction: 'ltr' },
  { code: 'hu', name: 'Hungarian', nativeName: 'Magyar', isSupported: true, regions: ['HU'], direction: 'ltr' },
  { code: 'ro', name: 'Romanian', nativeName: 'Română', isSupported: true, regions: ['RO', 'MD'], direction: 'ltr' },
  { code: 'el', name: 'Greek', nativeName: 'Ελληνικά', isSupported: true, regions: ['GR', 'CY'], direction: 'ltr' },
  { code: 'hr', name: 'Croatian', nativeName: 'Hrvatski', isSupported: true, regions: ['HR', 'BA'], direction: 'ltr' },
  { code: 'uk', name: 'Ukrainian', nativeName: 'Українська', isSupported: true, regions: ['UA'], direction: 'ltr' },
  { code: 'th', name: 'Thai', nativeName: 'ไทย', isSupported: true, regions: ['TH'], direction: 'ltr' },
  { code: 'vi', name: 'Vietnamese', nativeName: 'Tiếng Việt', isSupported: true, regions: ['VN'], direction: 'ltr' },
  { code: 'id', name: 'Indonesian', nativeName: 'Bahasa Indonesia', isSupported: true, regions: ['ID'], direction: 'ltr' },
  { code: 'ms', name: 'Malay', nativeName: 'Bahasa Melayu', isSupported: true, regions: ['MY', 'BN'], direction: 'ltr' },
  { code: 'tl', name: 'Filipino', nativeName: 'Filipino', isSupported: true, regions: ['PH'], direction: 'ltr' },
  { code: 'bn', name: 'Bengali', nativeName: 'বাংলা', isSupported: true, regions: ['BD', 'IN'], direction: 'ltr' },
  { code: 'ta', name: 'Tamil', nativeName: 'தமிழ்', isSupported: true, regions: ['IN', 'LK', 'SG', 'MY'], direction: 'ltr' },
  { code: 'te', name: 'Telugu', nativeName: 'తెలుగు', isSupported: true, regions: ['IN'], direction: 'ltr' },
  { code: 'mr', name: 'Marathi', nativeName: 'मराठी', isSupported: true, regions: ['IN'], direction: 'ltr' },
  { code: 'gu', name: 'Gujarati', nativeName: 'ગુજરાતી', isSupported: true, regions: ['IN'], direction: 'ltr' },
  { code: 'kn', name: 'Kannada', nativeName: 'ಕನ್ನಡ', isSupported: true, regions: ['IN'], direction: 'ltr' },
  { code: 'ml', name: 'Malayalam', nativeName: 'മലയാളം', isSupported: true, regions: ['IN'], direction: 'ltr' },
  { code: 'pa', name: 'Punjabi', nativeName: 'ਪੰਜਾਬੀ', isSupported: true, regions: ['IN', 'PK'], direction: 'ltr' },
  { code: 'ur', name: 'Urdu', nativeName: 'اردو', isSupported: true, regions: ['PK', 'IN'], direction: 'rtl' },
  { code: 'fa', name: 'Persian (Farsi)', nativeName: 'فارسی', isSupported: true, regions: ['IR', 'AF', 'TJ'], direction: 'rtl' },
  { code: 'he', name: 'Hebrew', nativeName: 'עברית', isSupported: true, regions: ['IL'], direction: 'rtl' },
  { code: 'sw', name: 'Swahili', nativeName: 'Kiswahili', isSupported: true, regions: ['KE', 'TZ', 'UG', 'CD', 'RW', 'BI'], direction: 'ltr' },
  { code: 'am', name: 'Amharic', nativeName: 'አማርኛ', isSupported: true, regions: ['ET'], direction: 'ltr' },
  { code: 'yo', name: 'Yoruba', nativeName: 'Yorùbá', isSupported: true, regions: ['NG', 'BJ', 'TG'], direction: 'ltr' },
  { code: 'ig', name: 'Igbo', nativeName: 'Igbo', isSupported: true, regions: ['NG'], direction: 'ltr' },
  { code: 'ha', name: 'Hausa', nativeName: 'Hausa', isSupported: true, regions: ['NG', 'NE', 'GH'], direction: 'ltr' },
  { code: 'zu', name: 'Zulu', nativeName: 'isiZulu', isSupported: true, regions: ['ZA'], direction: 'ltr' },
  { code: 'af', name: 'Afrikaans', nativeName: 'Afrikaans', isSupported: true, regions: ['ZA', 'NA'], direction: 'ltr' },
  { code: 'ca', name: 'Catalan', nativeName: 'Català', isSupported: true, regions: ['ES'], direction: 'ltr' },
  { code: 'eu', name: 'Basque', nativeName: 'Euskara', isSupported: true, regions: ['ES', 'FR'], direction: 'ltr' },
  { code: 'gl', name: 'Galician', nativeName: 'Galego', isSupported: true, regions: ['ES'], direction: 'ltr' },
  { code: 'bg', name: 'Bulgarian', nativeName: 'Български', isSupported: true, regions: ['BG'], direction: 'ltr' },
  { code: 'sr', name: 'Serbian', nativeName: 'Српски', isSupported: true, regions: ['RS', 'BA', 'ME'], direction: 'ltr' },
  { code: 'sk', name: 'Slovak', nativeName: 'Slovenčina', isSupported: true, regions: ['SK'], direction: 'ltr' },
  { code: 'sl', name: 'Slovenian', nativeName: 'Slovenščina', isSupported: true, regions: ['SI'], direction: 'ltr' },
  { code: 'lt', name: 'Lithuanian', nativeName: 'Lietuvių', isSupported: true, regions: ['LT'], direction: 'ltr' },
  { code: 'lv', name: 'Latvian', nativeName: 'Latviešu', isSupported: true, regions: ['LV'], direction: 'ltr' },
  { code: 'et', name: 'Estonian', nativeName: 'Eesti', isSupported: true, regions: ['EE'], direction: 'ltr' },
  { code: 'ka', name: 'Georgian', nativeName: 'ქართული', isSupported: true, regions: ['GE'], direction: 'ltr' },
  { code: 'hy', name: 'Armenian', nativeName: 'Հայերեն', isSupported: true, regions: ['AM'], direction: 'ltr' },
  { code: 'az', name: 'Azerbaijani', nativeName: 'Azərbaycan', isSupported: true, regions: ['AZ'], direction: 'ltr' },
  { code: 'kk', name: 'Kazakh', nativeName: 'Қазақ', isSupported: true, regions: ['KZ'], direction: 'ltr' },
  { code: 'uz', name: 'Uzbek', nativeName: 'Oʻzbek', isSupported: true, regions: ['UZ'], direction: 'ltr' },
  { code: 'km', name: 'Khmer', nativeName: 'ខ្មែរ', isSupported: true, regions: ['KH'], direction: 'ltr' },
  { code: 'my', name: 'Burmese', nativeName: 'မြန်မာ', isSupported: true, regions: ['MM'], direction: 'ltr' },
  { code: 'ne', name: 'Nepali', nativeName: 'नेपाली', isSupported: true, regions: ['NP'], direction: 'ltr' },
  { code: 'si', name: 'Sinhala', nativeName: 'සිංහල', isSupported: true, regions: ['LK'], direction: 'ltr' },
  { code: 'mn', name: 'Mongolian', nativeName: 'Монгол', isSupported: true, regions: ['MN'], direction: 'ltr' },
  { code: 'lo', name: 'Lao', nativeName: 'ລາວ', isSupported: true, regions: ['LA'], direction: 'ltr' },
  { code: 'so', name: 'Somali', nativeName: 'Soomaali', isSupported: true, regions: ['SO'], direction: 'ltr' },
  { code: 'rw', name: 'Kinyarwanda', nativeName: 'Ikinyarwanda', isSupported: true, regions: ['RW'], direction: 'ltr' },
]

// ── Helpers ──
export function getMarketsByRegion(region: string): Market[] {
  return MARKETS.filter(m => m.region === region)
}

export function get247Markets(): Market[] {
  return MARKETS.filter(m => m.is247)
}

export function getMarketsByAssetType(type: Market['assetTypes'][number]): Market[] {
  return MARKETS.filter(m => m.assetTypes.includes(type))
}

export function getAllRegions(): string[] {
  return [...new Set(MARKETS.map(m => m.region))].sort()
}

export function getAllAssetTypes(): string[] {
  return [...new Set(MARKETS.flatMap(m => m.assetTypes))].sort()
}

export function getLanguagesByRegion(countryCode: string): Language[] {
  return LANGUAGES.filter(l => l.regions.includes(countryCode))
}

export function getRTLLanguages(): Language[] {
  return LANGUAGES.filter(l => l.direction === 'rtl')
}
