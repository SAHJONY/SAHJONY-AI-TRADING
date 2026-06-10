import Link from 'next/link';
import { MessageSquare } from 'lucide-react';

export default function FloatingChatButton() {
  return (
    <Link
      href="/conversations"
      className="fixed bottom-6 right-6 bg-primary text-white rounded-full w-14 h-14 flex items-center justify-center shadow-lg hover:bg-primary-hover transition-colors z-50"
    >
      <MessageSquare className="h-6 w-6" />
    </Link>
  );
}
