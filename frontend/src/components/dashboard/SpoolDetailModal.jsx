import React from 'react';
import { createPortal } from 'react-dom';
import SpoolDetailPanel from './SpoolDetailPanel';

export default function SpoolDetailModal({
  spool,
  history,
  loading,
  onClose,
  onHistoryUpdate,
  onRecordUsage,
}) {
  if (!spool) return null;

  return createPortal(
    <div className="modal-overlay spool-detail-overlay" onClick={onClose}>
      <div className="spool-detail-panel-container" onClick={(event) => event.stopPropagation()}>
        <SpoolDetailPanel
          spool={spool}
          history={history}
          onClose={onClose}
          onHistoryUpdate={onHistoryUpdate}
          onRecordUsage={onRecordUsage}
        />
        {loading && (
          <div className="spool-detail-loading">
            <div className="loading-spinner" />
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
