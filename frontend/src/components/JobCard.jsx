/**
 * Individual job card component
 */

import StatusBadge from './StatusBadge';
import { API_BASE } from '../api/client';

export default function JobCard({ job, onRefresh }) {
    const formatDate = (dateString) => {
        return new Date(dateString).toLocaleString();
    };

    const getFilename = (path) => {
        return path.split('/').pop();
    };

    return (
        <div className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow">
            <div className="flex justify-between items-start mb-4">
                <div className="flex-1">
                    <h3 className="text-lg font-semibold text-gray-900 mb-1">
                        {getFilename(job.filename)}
                    </h3>
                    <p className="text-sm text-gray-600">
                        Profile: <span className="font-medium">{job.profile_id}</span>
                    </p>
                </div>
                <StatusBadge status={job.status} />
            </div>

            <div className="space-y-2 text-sm text-gray-600">
                <div className="flex justify-between">
                    <span>Created:</span>
                    <span className="font-medium">{formatDate(job.created_at)}</span>
                </div>

                {job.current_stage && (
                    <div className="flex justify-between">
                        <span>Current Stage:</span>
                        <span className="font-medium">{job.current_stage}</span>
                    </div>
                )}

                {job.completed_at && (
                    <div className="flex justify-between">
                        <span>Completed:</span>
                        <span className="font-medium">{formatDate(job.completed_at)}</span>
                    </div>
                )}

                {job.error && (
                    <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded">
                        <p className="text-red-700 text-xs">{job.error}</p>
                    </div>
                )}
            </div>

            {job.outputs && job.outputs.length > 0 && (
                <div className="mt-4 pt-4 border-t border-gray-200">
                    <p className="text-sm font-medium text-gray-700 mb-2">Outputs:</p>
                    <div className="space-y-1">
                        {job.outputs.map((output, idx) => (
                            <a
                                key={idx}
                                href={`${API_BASE}${output.path}`}
                                download
                                className="block text-sm text-blue-600 hover:text-blue-800 hover:underline"
                            >
                                📄 {output.name}
                            </a>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
