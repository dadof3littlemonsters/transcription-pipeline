/**
 * Main dashboard component
 */

import { useState } from 'react';
import FileUpload from './FileUpload';
import JobList from './JobList';

export default function Dashboard() {
    const [refreshKey, setRefreshKey] = useState(0);

    const handleUploadSuccess = () => {
        // Trigger job list refresh by changing key
        setRefreshKey(prev => prev + 1);
    };

    return (
        <div className="min-h-screen bg-gray-100">
            <header className="bg-white shadow-sm">
                <div className="max-w-7xl mx-auto px-4 py-6">
                    <h1 className="text-3xl font-bold text-gray-900">
                        Transcription Pipeline Control Hub
                    </h1>
                </div>
            </header>

            <main className="max-w-7xl mx-auto px-4 py-8">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                    {/* Upload Section */}
                    <div className="lg:col-span-1">
                        <FileUpload onUploadSuccess={handleUploadSuccess} />
                    </div>

                    {/* Jobs Section */}
                    <div className="lg:col-span-2">
                        <JobList key={refreshKey} />
                    </div>
                </div>
            </main>
        </div>
    );
}
