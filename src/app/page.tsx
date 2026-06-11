// src/app/page.tsx
// Ultra‑premium, cinematic landing page – Tesla‑style design

import Image from 'next/image';
import Link from 'next/link';
import Head from 'next/head';
import FloatingChatBubble from '@/components/FloatingChatBubble';

export default async function LandingPage() {
  // Placeholder Supabase auth – real implementation to be added later
  const supabase = await (async () => ({ auth: { getUser: async () => ({ data: { user: null } }) } }))();
  const { data: { user } } = await supabase.auth.getUser();

  return (
    <>
      <Head>
        <title>Sahjony Capital – AI‑Powered Autonomous Trading</title>
        <meta name="description" content="Cutting‑edge, photorealistic AI trading platform with Tesla‑inspired design." />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="icon" href="/favicon.ico" />
      </Head>
      {/* Full‑screen cinematic background video */}
      <section className="relative h-screen w-full overflow-hidden">
        {/* Background video – replace src with your own 8K cinematic clip */}
        <video
          className="absolute inset-0 w-full h-full object-cover"
          src="https://assets.mixkit.co/videos/preview/mixkit-forest-winter-river-running-through-trees-2020-large.mp4"
          autoPlay
          muted
          loop
          playsInline
        />
        {/* Dark overlay for readability */}
        <div className="absolute inset-0 bg-black/60" />
        {/* Hero content */}
        <div className="relative z-10 flex h-full flex-col items-center justify-center text-center px-4 lg:px-0">
          <h1 className="text-6xl md:text-8xl font-extrabold bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-purple-500 drop-shadow-lg mb-6">
            Sahjony Capital
          </h1>
          <p className="max-w-2xl text-xl md:text-2xl text-white/90 mb-8">
            AI‑driven autonomous trading at the speed of light – a Tesla‑style experience for capital markets.
          </p>
          <div className="flex flex-col sm:flex-row gap-4">
            <Link
              href="/dashboard"
              className="inline-block bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-4 px-8 rounded-full shadow-lg transition"
            >
              Go to Dashboard
            </Link>
            <Link
              href="#waitlist"
              className="inline-block bg-gray-800 hover:bg-gray-700 text-white font-medium py-4 px-8 rounded-full border border-white/20 transition"
            >
              Join Waitlist
            </Link>
          </div>
        </div>
      </section>

      {/* Feature sections – high‑resolution images with Next.js Image for 8K quality */}
      <section className="bg-gray-950 text-gray-100 py-20" id="features">
        <div className="container mx-auto px-6 lg:px-12 grid md:grid-cols-3 gap-12">
          <FeatureCard
            title="Strategy Engine"
            description="AI agents generate multi‑frequency signals, optimized through real‑time back‑testing on petabytes of market data."
            imgUrl="https://images.unsplash.com/photo-1519389950473-47ba0277781c?auto=format&fit=crop&w=3840&q=80"
          />
          <FeatureCard
            title="Risk Management"
            description="Dynamic VaR, drawdown limits, and capital allocation protect assets across 60+ exchanges."
            imgUrl="https://images.unsplash.com/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=3840&q=80"
          />
          <FeatureCard
            title="Execution Layer"
            description="Low‑latency order routing, smart order routing, and multi‑exchange connectivity at micro‑second speeds."
            imgUrl="https://images.unsplash.com/photo-1521737604893-d14cc237f11d?auto=format&fit=crop&w=3840&q=80"
          />
        </div>
      </section>

      {/* Waitlist CTA – sleek modal‑style form */}
      <section className="bg-gray-900 py-20" id="waitlist">
        <div className="container mx-auto px-6 lg:px-12 text-center">
          <h2 className="text-4xl md:text-5xl font-bold text-indigo-400 mb-6">Early Access Program</h2>
          <p className="max-w-2xl mx-auto text-lg text-gray-300 mb-8">
            Join our private alpha to test the platform, receive updates, and shape the product roadmap.
          </p>
          <form className="max-w-xl mx-auto space-y-4" method="POST" action="/api/waitlist">
            <input
              type="text"
              name="name"
              required
              placeholder="Your name"
              className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <input
              type="email"
              name="email"
              required
              placeholder="Email address"
              className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button
              type="submit"
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-3 rounded-full transition"
            >
              Join Waitlist
            </button>
          </form>
        </div>
      </section>

      {/* Footer – minimalist, Tesla‑inspired */}
      <footer className="bg-gray-950 text-gray-500 py-6">
        <div className="container mx-auto px-6 lg:px-12 text-center">
          © {new Date().getFullYear()} Sahjony Capital • All Rights Reserved
        </div>
      </footer>
    <div className="mt-12 text-center">
        <Image
          src="https://images.unsplash.com/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=1920&q=80"
          alt="Standard UI background"
          width={1200}
          height={800}
          className="rounded-lg shadow-lg mx-auto"
          priority={true}
        />
      </div>
    <FloatingChatBubble />
    </>
  );
}

function FeatureCard({ title, description, imgUrl }: { title: string; description: string; imgUrl: string }) {
  return (
    <div className="bg-gray-800 rounded-xl overflow-hidden shadow-lg hover:shadow-2xl transition-shadow">
      <Image
        src={imgUrl}
        alt={title}
        width={1200}
        height={800}
        className="object-cover w-full h-48 md:h-64"
        priority={true}
      />
      <div className="p-6">
        <h3 className="text-2xl font-semibold text-indigo-400 mb-3">{title}</h3>
        <p className="text-gray-300 text-sm md:text-base">{description}</p>
      </div>
    </div>
  );
}
