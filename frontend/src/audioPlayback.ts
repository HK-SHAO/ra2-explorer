import { useSyncExternalStore } from "react";

import { cachedAudioResourceUrl, cancelAudioResourcePreload } from "./resourcePreload";

interface AudioPlaybackState {
  assetId: string;
  playing: boolean;
  loading: boolean;
}

interface AudioProgressState {
  assetId: string;
  currentTime: number;
  duration: number;
}

const listeners = new Set<() => void>();
const progressListeners = new Set<() => void>();
let playbackState: AudioPlaybackState = { assetId: "", playing: false, loading: false };
let progressState: AudioProgressState = { assetId: "", currentTime: 0, duration: 0 };
let sharedAudio: HTMLAudioElement | null = null;
let sourceUrl = "";

function publish(next: AudioPlaybackState) {
  if (
    next.assetId === playbackState.assetId
    && next.playing === playbackState.playing
    && next.loading === playbackState.loading
  ) return;
  playbackState = next;
  for (const listener of listeners) listener();
}

// Progress lives in its own channel so the frequent timeupdate tick only
// re-renders the progress bar instead of every play button on screen.
function publishProgress(next: AudioProgressState) {
  if (
    next.assetId === progressState.assetId
    && next.currentTime === progressState.currentTime
    && next.duration === progressState.duration
  ) return;
  progressState = next;
  for (const listener of progressListeners) listener();
}

function readProgress() {
  if (!sharedAudio) return;
  publishProgress({
    assetId: playbackState.assetId,
    currentTime: sharedAudio.currentTime,
    duration: Number.isFinite(sharedAudio.duration) ? sharedAudio.duration : 0,
  });
}

function audioElement() {
  if (sharedAudio) return sharedAudio;
  const audio = new Audio();
  audio.preload = "auto";
  audio.addEventListener("loadstart", () => publish({ assetId: playbackState.assetId, playing: false, loading: true }));
  audio.addEventListener("waiting", () => publish({ assetId: playbackState.assetId, playing: false, loading: true }));
  audio.addEventListener("playing", () => publish({ assetId: playbackState.assetId, playing: true, loading: false }));
  audio.addEventListener("pause", () => publish({ assetId: playbackState.assetId, playing: false, loading: false }));
  audio.addEventListener("ended", () => publish({ assetId: playbackState.assetId, playing: false, loading: false }));
  audio.addEventListener("error", () => publish({ assetId: playbackState.assetId, playing: false, loading: false }));
  audio.addEventListener("timeupdate", readProgress);
  audio.addEventListener("durationchange", readProgress);
  audio.addEventListener("seeked", readProgress);
  sharedAudio = audio;
  return audio;
}

export function getAudioPlaybackState() {
  return playbackState;
}

export function subscribeAudioPlayback(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function useAudioPlayback() {
  return useSyncExternalStore(subscribeAudioPlayback, getAudioPlaybackState, getAudioPlaybackState);
}

export function getAudioProgress() {
  return progressState;
}

export function subscribeAudioProgress(listener: () => void) {
  progressListeners.add(listener);
  return () => {
    progressListeners.delete(listener);
  };
}

export function useAudioProgress() {
  return useSyncExternalStore(subscribeAudioProgress, getAudioProgress, getAudioProgress);
}

export function playAudioAsset(assetId: string, url: string) {
  const audio = audioElement();
  const cachedUrl = cachedAudioResourceUrl(url);
  const playableUrl = cachedUrl || url;
  if (!cachedUrl) cancelAudioResourcePreload(url);
  if (playbackState.assetId !== assetId || sourceUrl !== playableUrl) {
    audio.pause();
    sourceUrl = playableUrl;
    publish({ assetId, playing: false, loading: true });
    publishProgress({ assetId, currentTime: 0, duration: 0 });
    audio.src = playableUrl;
    audio.preload = "auto";
  }
  return audio.play().catch(() => {
    publish({ assetId, playing: false, loading: false });
  });
}

export function pauseAudioAsset(assetId?: string) {
  if (assetId && playbackState.assetId !== assetId) return;
  sharedAudio?.pause();
}

export function seekAudioAsset(seconds: number) {
  if (!sharedAudio || !Number.isFinite(sharedAudio.duration)) return;
  sharedAudio.currentTime = Math.min(Math.max(seconds, 0), sharedAudio.duration);
  readProgress();
}

export function toggleAudioAsset(assetId: string, url: string) {
  const audio = audioElement();
  if (playbackState.assetId === assetId && (!audio.paused || playbackState.loading)) {
    audio.pause();
    return;
  }
  void playAudioAsset(assetId, url);
}
