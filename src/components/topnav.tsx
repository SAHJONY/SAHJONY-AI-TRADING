export default function TopNav() {
  return (
    <nav className="bg-surface-elevated p-4 text-white flex justify-between items-center">
      <div className="flex items-center space-x-2">
        <span className="font-bold">Sahjony</span>
      </div>
      <div className="space-x-4">
        <a href="/" className="hover:underline">Home</a>
        <a href="/dashboard" className="hover:underline">Dashboard</a>
        <a href="/login" className="hover:underline">Login</a>
      </div>
    </nav>
  );
}
