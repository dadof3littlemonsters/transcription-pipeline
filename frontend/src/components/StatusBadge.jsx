/**
 * Status badge component with color coding
 */

const STATUS_STYLES = {
    QUEUED: 'bg-status-queued text-white',
    PROCESSING: 'bg-status-processing text-white',
    COMPLETE: 'bg-status-complete text-white',
    FAILED: 'bg-status-failed text-white',
    CANCELLED: 'bg-status-cancelled text-white',
};

export default function StatusBadge({ status }) {
    const styles = STATUS_STYLES[status] || 'bg-gray-400 text-white';

    return (
        <span className={`px-3 py-1 rounded-full text-xs font-semibold ${styles}`}>
            {status}
        </span>
    );
}
