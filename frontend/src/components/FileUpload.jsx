/**
 * File upload component with drag-and-drop
 */

import { useState, useEffect } from 'react';
import { api } from '../api/client';

export default function FileUpload({ onUploadSuccess }) {
    const [profiles, setProfiles] = useState([]);
    const [selectedProfile, setSelectedProfile] = useState('');
    const [file, setFile] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState(null);
    const [dragActive, setDragActive] = useState(false);

    useEffect(() => {
        // Fetch profiles on mount
        api.getProfiles()
            .then(data => {
                setProfiles(data);
                if (data.length > 0) {
                    setSelectedProfile(data[0].id);
                }
            })
            .catch(err => console.error('Failed to load profiles:', err));
    }, []);

    const handleDrag = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActive(true);
        } else if (e.type === "dragleave") {
            setDragActive(false);
        }
    };

    const handleDrop = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);

        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            setFile(e.dataTransfer.files[0]);
        }
    };

    const handleFileChange = (e) => {
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0]);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();

        if (!file || !selectedProfile) {
            setError('Please select a file and profile');
            return;
        }

        setUploading(true);
        setError(null);

        try {
            const job = await api.createJob(file, selectedProfile);
            setFile(null);
            if (onUploadSuccess) {
                onUploadSuccess(job);
            }
        } catch (err) {
            setError(err.message);
        } finally {
            setUploading(false);
        }
    };

    return (
        <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-2xl font-bold text-gray-900 mb-4">Upload Audio File</h2>

            <form onSubmit={handleSubmit} className="space-y-4">
                {/* Profile Selector */}
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                        Profile
                    </label>
                    <select
                        value={selectedProfile}
                        onChange={(e) => setSelectedProfile(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                        {profiles.map((profile) => (
                            <option key={profile.id} value={profile.id}>
                                {profile.name} ({profile.stage_count} stages)
                            </option>
                        ))}
                    </select>
                </div>

                {/* Drag and Drop Zone */}
                <div
                    onDragEnter={handleDrag}
                    onDragLeave={handleDrag}
                    onDragOver={handleDrag}
                    onDrop={handleDrop}
                    className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${dragActive
                            ? 'border-blue-500 bg-blue-50'
                            : 'border-gray-300 hover:border-gray-400'
                        }`}
                >
                    <input
                        type="file"
                        id="file-upload"
                        onChange={handleFileChange}
                        accept="audio/*,video/*"
                        className="hidden"
                    />

                    {file ? (
                        <div className="space-y-2">
                            <p className="text-green-600 font-medium">✓ {file.name}</p>
                            <p className="text-sm text-gray-600">
                                {(file.size / 1024 / 1024).toFixed(2)} MB
                            </p>
                            <button
                                type="button"
                                onClick={() => setFile(null)}
                                className="text-sm text-red-600 hover:text-red-800"
                            >
                                Remove
                            </button>
                        </div>
                    ) : (
                        <div className="space-y-2">
                            <p className="text-gray-600">
                                Drag and drop your audio file here, or
                            </p>
                            <label
                                htmlFor="file-upload"
                                className="inline-block px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 cursor-pointer"
                            >
                                Choose File
                            </label>
                        </div>
                    )}
                </div>

                {error && (
                    <div className="bg-red-50 border border-red-200 rounded-md p-3">
                        <p className="text-red-700 text-sm">{error}</p>
                    </div>
                )}

                <button
                    type="submit"
                    disabled={!file || uploading}
                    className="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed font-medium"
                >
                    {uploading ? 'Uploading...' : 'Upload and Transcribe'}
                </button>
            </form>
        </div>
    );
}
