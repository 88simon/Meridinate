/**
 * Health check endpoint for Docker container monitoring
 * Returns 200 OK if the application is running
 */
export async function GET() {
  return Response.json(
    {
      status: 'healthy',
      timestamp: new Date().toISOString(),
      service: 'gun-del-sol-web'
    },
    { status: 200 }
  );
}
