import { redirect } from 'next/navigation';

export default function TokensRedirect() {
  redirect('/dashboard/bot-tracker');
}
