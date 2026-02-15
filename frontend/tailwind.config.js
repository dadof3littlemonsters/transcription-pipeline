/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                'status-queued': '#6b7280',
                'status-processing': '#3b82f6',
                'status-complete': '#10b981',
                'status-failed': '#ef4444',
                'status-cancelled': '#f59e0b',
            },
        },
    },
    plugins: [],
}
