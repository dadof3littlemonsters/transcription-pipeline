/**
 * Job list component with auto-refresh
 */

import { useState, useEffect } from 'react';
import { api } from '../api/client';
import JobCard from './JobCard';

export default function JobList() {
    const [jobs, setJobs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchJobs = async () => {
        try {
            const data = await api.getJobs({ limit: 20 });
            setJobs(data.jobs);
            setError(null);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchJobs();

        // Poll for updates every 5 seconds
        const interval = setInterval(fetchJobs, 5000);

        return () => clearInterval(interval);
    }, []);

    if (loading) {
        return (
            <div className="flex justify-center items-center h-64">
                <div className="text-gray-600">Loading jobs...</div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <p className="text-red-700">Error loading jobs: {error}</p>
                <button
                    onClick={fetchJobs}
                    className="mt-2 text-sm text-red-600 hover:text-red-800 underline"
                >
                    Retry
                </button>
            </div>
        );
    }

    if (jobs.length === 0) {
        return (
            <div className="text-center py-12 bg-gray-50 rounded-lg">
                <p className="text-gray-600">No jobs yet. Upload a file to get started!</p>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <div className="flex justify-between items-center mb-4">
                <h2 className="text-2xl font-bold text-gray-900">Jobs</h2>
                <button
                    onClick={fetchJobs}
                    className="text-sm text-blue-600 hover:text-blue-800"
                >
                    🔄 Refresh
                </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {jobs.map((job) => (
                    <JobCard key={job.id} job={job} onRefresh={fetchJobs} />
                ))}
            </div>
        </div>
    );
}
