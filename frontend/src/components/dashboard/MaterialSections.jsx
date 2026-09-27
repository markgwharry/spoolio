import React from 'react';
import EmptyState from '../EmptyState';
import RefillListItem from './RefillListItem';
import SpoolListItem from './SpoolListItem';
import SpoolTile from './SpoolTile';

const slug = (value) => String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '-');

export default function MaterialSections({
  groupedSpools,
  spools,
  refills,
  emptySpools,
  materials,
  colors,
  manufacturers,
  spoolTypes,
  expanded,
  collapsed,
  highlightedSpoolId,
  onToggleGroup,
  onToggleMaterial,
  onOpenSpoolDetail,
  onSpoolUpdated,
  onSpoolDeleted,
  onAssembleRefill,
  onDeleteRefill,
}) {
  const groupsAreEmpty = Object.values(groupedSpools)
    .every((colorGroups) => Object.keys(colorGroups).length === 0);

  return (
    <div className="material-sections">
      {groupsAreEmpty && (
        <EmptyState
          title="No spools match your filters"
          message="Try clearing a filter or the low-stock toggle to see more."
        />
      )}
      {Object.entries(groupedSpools).map(([material, colorGroups]) => {
        if (Object.keys(colorGroups).length === 0) return null;
        const materialId = materials.find((entry) => entry.name === material)?.id;
        const materialSpools = spools.filter(
          (spool) => !spool.is_empty && spool.material_id === materialId,
        );
        const materialWeight = materialSpools.reduce(
          (sum, spool) => sum + (spool.weight_remaining || 0),
          0,
        );

        return (
          <section key={material} className="material-section">
            <button
              type="button"
              className="material-header"
              onClick={() => onToggleMaterial(material)}
              aria-expanded={!collapsed[material]}
              aria-label={`${collapsed[material] ? 'Expand' : 'Collapse'} ${material} section`}
            >
              <span className="collapse-btn" aria-hidden="true">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  {collapsed[material] ? (
                    <polyline points="9 18 15 12 9 6" />
                  ) : (
                    <polyline points="6 9 12 15 18 9" />
                  )}
                </svg>
              </span>
              <h2>{material}</h2>
              <span className="material-meta">
                {materialSpools.length} {materialSpools.length === 1 ? 'spool' : 'spools'} · {(materialWeight / 1000).toFixed(1)}kg
              </span>
              <div className="material-line" />
            </button>
            {!collapsed[material] && (
              <>
                <div className="spool-grid">
                  {Object.entries(colorGroups).map(([color, spoolsInGroup]) => {
                    const groupKey = `${material}-${color}`;
                    const activeSpools = spoolsInGroup.filter((spool) => !spool.is_empty);
                    const totalWeight = activeSpools.reduce(
                      (sum, spool) => sum + (spool.weight_remaining || 0),
                      0,
                    );
                    const colorId = spoolsInGroup[0]?.color_id
                      || colors.find((entry) => entry.name === color)?.id;
                    const refillsInGroup = refills.filter(
                      (refill) => refill.material_id === materialId && refill.color_id === colorId,
                    );
                    const reserveWeight = refillsInGroup.reduce(
                      (sum, refill) => sum + (refill.weight_remaining ?? refill.weight_total ?? 0),
                      0,
                    );
                    const isLowStock = spoolsInGroup.some(
                      (spool) => !spool.is_empty
                        && spool.weight_remaining <= (spool.low_stock_threshold ?? 100),
                    );

                    return (
                      <div
                        key={groupKey}
                        id={`group-${slug(groupKey)}`}
                        className={`spool-grid-item${expanded[groupKey] ? ' is-expanded' : ''}`}
                      >
                        <SpoolTile
                          color={color}
                          count={activeSpools.length}
                          totalWeight={totalWeight}
                          reserveCount={refillsInGroup.length}
                          reserveWeight={reserveWeight}
                          faded={spoolsInGroup.length > 0 && spoolsInGroup.every((spool) => spool.is_empty)}
                          onClick={() => onToggleGroup(groupKey)}
                          highlight={isLowStock}
                        />
                        {expanded[groupKey] && (spoolsInGroup.length > 0 || refillsInGroup.length > 0) && (
                          <div className="expand-panel open horizontal-spool-panel">
                            <div className="horizontal-spool-list">
                              {spoolsInGroup.map((spool) => (
                                <SpoolListItem
                                  key={spool.id}
                                  spool={spool}
                                  highlighted={highlightedSpoolId === spool.id}
                                  onShowDetail={onOpenSpoolDetail}
                                  onUpdate={onSpoolUpdated}
                                  onDelete={onSpoolDeleted}
                                />
                              ))}
                              {activeSpools.length === 0 && spoolsInGroup.length === 0 && (
                                <div className="empty-spools-notice">No active spools for this colour.</div>
                              )}
                            </div>
                            {refillsInGroup.length > 0 && (
                              <div className="refills-section">
                                <div className="refills-header">Refills available</div>
                                <div className="horizontal-spool-list">
                                  {refillsInGroup.map((refill) => (
                                    <RefillListItem
                                      key={`refill-${refill.id}`}
                                      refill={refill}
                                      manufacturers={manufacturers}
                                      emptySpools={emptySpools}
                                      spoolTypes={spoolTypes}
                                      onAssemble={onAssembleRefill}
                                      onDelete={onDeleteRefill}
                                    />
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </section>
        );
      })}
    </div>
  );
}
