import { redirect } from 'next/navigation';

export default function HomePage() {
  // Redirect to tokens page
  redirect('/dashboard/tokens');
}
