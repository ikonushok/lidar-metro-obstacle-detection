'use strict';

const eventReview = document.getElementById('event-review');
const eventTrack = document.getElementById('event-track');
const eventDetail = document.createElement('span');
eventDetail.id = 'event-detail';
let eventReviewDataset = null;
let selectedUnlocalizedObject = null;
const alarmFrameMarkers = new Set();

function addAlarmMarker(index, source) {
  if (!Number.isInteger(index) || alarmFrameMarkers.has(index)) return;
  alarmFrameMarkers.add(index);
  const marker = document.createElement('button');
  marker.type = 'button';
  marker.className = 'observed-alarm';
  marker.style.left = `${100 * index / Math.max(1, manifest.frames.length - 1)}%`;
  marker.title = `C++: тревога, кадр ${index} (${source})`;
  marker.setAttribute('aria-label', marker.title);
  marker.onclick = () => showNow(index);
  eventTrack.appendChild(marker);
}

function updateEventReview() {
  const objects = manifest?.review_objects || [];
  eventReview.hidden = objects.length === 0;
  if (eventReviewDataset !== manifest?.dataset_id) {
    eventReviewDataset = manifest?.dataset_id;
    selectedUnlocalizedObject = null;
    alarmFrameMarkers.clear();
    eventReview.replaceChildren(eventDetail);
    eventTrack.replaceChildren();
    for (const item of objects) {
      const window = item.frames_inclusive;
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = item.object_id.slice(3);
      button.dataset.objectId = item.object_id;
      button.className = window ? '' : 'unlocalized';
      if (item.working_role !== 'positive' && item.working_role !== 'positive_review') {
        button.classList.add('negative');
      }
      const reviewNote = item.review_status === 'ambiguous_excluded' ?
        'объект не подтверждён; исключён из анализа' :
        'не локализован; исключён из анализа';
      button.title = `${item.description_ru} · ${window ?
        `виден на кадрах ${window[0]}–${window[1]} (разметка пользователя)` : reviewNote}`;
      button.setAttribute('aria-label', `Объект ${item.object_id.slice(3)}: ${button.title}`);
      button.onclick = () => {
        if (window) showNow(window[0]);
        else {
          selectedUnlocalizedObject = item.object_id;
          updateEventReview();
        }
      };
      eventReview.appendChild(button);
      if (window) {
        const marker = document.createElement('button');
        marker.type = 'button';
        marker.className = button.className;
        marker.style.left = `${100 * window[0] / Math.max(1, manifest.frames.length - 1)}%`;
        marker.title = button.title;
        marker.setAttribute('aria-label', button.getAttribute('aria-label'));
        marker.onclick = () => showNow(window[0]);
        eventTrack.appendChild(marker);
      }
    }
    for (const index of manifest.review_alarm_frames || []) {
      addAlarmMarker(index, 'локальный полный прогон');
    }
  }

  if (result?.intrusion_candidate_present === true && current >= 0) {
    addAlarmMarker(current, 'текущий просмотр');
  }

  const active = objects.find(item => item.frames_inclusive &&
    current >= item.frames_inclusive[0] && current <= item.frames_inclusive[1]);
  const selected = active || objects.find(item => item.object_id === selectedUnlocalizedObject);
  for (const button of eventReview.querySelectorAll('button[data-object-id]')) {
    button.classList.toggle('active', button.dataset.objectId === selected?.object_id);
  }
  if (!selected) eventDetail.textContent = objects.length ? 'Контрольные объекты' : '';
  else if (!selected.frames_inclusive) eventDetail.textContent =
    `${selected.object_id}: ${selected.review_status === 'ambiguous_excluded' ?
      'объект не подтверждён; исключён из анализа' :
      'не локализован; исключён из анализа'}`;
  else {
    const decision = result?.intrusion_candidate_present === true ? 'C++: тревога' :
      earlyRunPresent() ? 'C++: ранний кандидат, 3 кадра (эксперимент)' :
      result?.status === 'OBSERVED_BOUNDARY_WARNING' ? 'C++: предупреждение у границы' :
      result?.status === 'UNKNOWN' || result?.intrusion_candidate_present == null ?
        'C++: UNKNOWN' : 'C++: нет тревоги';
    eventDetail.textContent = `${selected.object_id} · ${selected.description_ru} · ${decision}`;
  }

  const backendMode = result?.noise_filter_mode === 'baseline_v3';
  for (const id of ['noise-min-points', 'noise-radius', 'noise-max-axis-span',
    'noise-max-axis-distance', 'temporal-required-frames', 'train-moving',
    'temporal-near-zone-m', 'temporal-match-axis-m']) {
    const control = document.getElementById(id);
    control.disabled = backendMode;
    control.title = backendMode ? 'В режиме baseline_v3 решение принимает C++' : '';
  }
  if (backendMode) {
    const summary = document.getElementById('cpp-summary');
    summary.textContent = `C++ baseline_v3 · ${result.status} · рельсы: ${result.observed_rail_pair_count ?? 0}` +
      ` пар · CORE: ${result.core_count ?? 0} · подтверждено: ${result.intrusion_candidate_present === true ? result.reportable_core_count ?? 0 : 0}` +
      ` · ранний кандидат: ${result.experimental_early_core_count ?? 0}` +
      ` · margin: ${result.margin_count ?? 0} · ${result.reason ?? ''}`;
  }
}

new MutationObserver(updateEventReview).observe(document.getElementById('status'), {
  childList: true,
  characterData: true,
});
