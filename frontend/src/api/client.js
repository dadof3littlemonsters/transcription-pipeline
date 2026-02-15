/**
 * API client for transcription pipeline backend
 */

export const API_BASE = import.meta.env.VITE_API_URL || '';

export const api = {
    /**
     * Get list of jobs with optional filtering
     */
    async getJobs(params = {}) {
        const query = new URLSearchParams(params).toString();
        const url = `${API_BASE}/api/jobs${query ? `?${query}` : ''}`;
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to fetch jobs');
        return response.json();
    },

    /**
     * Get single job by ID
     */
    async getJob(id) {
        const response = await fetch(`${API_BASE}/api/jobs/${id}`);
        if (!response.ok) throw new Error(`Failed to fetch job ${id}`);
        return response.json();
    },

    /**
     * Create new transcription job
     */
    async createJob(file, profileId) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('profile_id', profileId);

        const response = await fetch(`${API_BASE}/api/jobs`, {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to create job');
        }

        return response.json();
    },

    /**
     * Delete/cancel job
     */
    async deleteJob(id) {
        const response = await fetch(`${API_BASE}/api/jobs/${id}`, {
            method: 'DELETE',
        });
        if (!response.ok) throw new Error(`Failed to delete job ${id}`);
    },

    /**
     * Get list of available profiles
     */
    async getProfiles() {
        const response = await fetch(`${API_BASE}/api/profiles`);
        if (!response.ok) throw new Error('Failed to fetch profiles');
        return response.json();
    },

    /**
     * Get profile details
     */
    async getProfile(id) {
        const response = await fetch(`${API_BASE}/api/profiles/${id}`);
        if (!response.ok) throw new Error(`Failed to fetch profile ${id}`);
        return response.json();
    },

    /**
     * Get system health status
     */
    async getHealth() {
        const response = await fetch(`${API_BASE}/health`);
        if (!response.ok) throw new Error('Failed to fetch health');
        return response.json();
    },
};
