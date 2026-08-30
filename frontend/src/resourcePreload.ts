export type ResourcePriority = "foreground" | "background";

interface ImageJob {
  url: string;
  priority: ResourcePriority;
  image: HTMLImageElement | null;
  resolve: (loaded: boolean) => void;
  promise: Promise<boolean>;
}

const completedCardPreviews = new Set<string>();
const pendingCardPreviews = new Map<string, ImageJob>();
const cardPreviewQueue: ImageJob[] = [];
const retainedCardImages = new Map<string, HTMLImageElement>();
const retainedCardImageLimit = 96;
const cardPreviewConcurrency = 6;
let activeCardPreviews = 0;
let backgroundPauseDepth = 0;

function retainDecodedCard(url: string, image: HTMLImageElement) {
  retainedCardImages.delete(url);
  retainedCardImages.set(url, image);
  while (retainedCardImages.size > retainedCardImageLimit) {
    const oldest = retainedCardImages.keys().next().value;
    if (oldest === undefined) break;
    retainedCardImages.delete(oldest);
  }
}

function finishCardPreview(job: ImageJob, loaded: boolean) {
  activeCardPreviews = Math.max(0, activeCardPreviews - 1);
  pendingCardPreviews.delete(job.url);
  if (loaded && job.image) {
    completedCardPreviews.add(job.url);
    retainDecodedCard(job.url, job.image);
  }
  job.resolve(loaded);
  drainCardPreviewQueue();
}

function startCardPreview(job: ImageJob) {
  activeCardPreviews += 1;
  const image = new Image();
  job.image = image;
  image.decoding = "async";
  image.fetchPriority = job.priority === "foreground" ? "high" : "low";
  image.onload = () => {
    if (typeof image.decode === "function") {
      void image.decode().catch(() => undefined).then(() => finishCardPreview(job, true));
    } else {
      finishCardPreview(job, true);
    }
  };
  image.onerror = () => finishCardPreview(job, false);
  image.src = job.url;
}

function drainCardPreviewQueue() {
  while (activeCardPreviews < cardPreviewConcurrency && cardPreviewQueue.length > 0) {
    const foregroundIndex = cardPreviewQueue.findIndex((job) => job.priority === "foreground");
    const nextIndex = foregroundIndex >= 0 ? foregroundIndex : backgroundPauseDepth > 0 ? -1 : 0;
    if (nextIndex < 0) return;
    const [job] = cardPreviewQueue.splice(nextIndex, 1);
    startCardPreview(job);
  }
}

export function hasLoadedCardPreview(url: string) {
  return completedCardPreviews.has(url);
}

export function preloadCardPreview(url: string, priority: ResourcePriority = "background") {
  if (!url) return Promise.resolve(false);
  if (completedCardPreviews.has(url)) return Promise.resolve(true);
  const pending = pendingCardPreviews.get(url);
  if (pending) {
    if (priority === "foreground" && pending.priority !== "foreground") {
      pending.priority = "foreground";
      if (pending.image) pending.image.fetchPriority = "high";
      drainCardPreviewQueue();
    }
    return pending.promise;
  }

  let resolveJob: (loaded: boolean) => void = () => {};
  const promise = new Promise<boolean>((resolve) => { resolveJob = resolve; });
  const job: ImageJob = { url, priority, image: null, resolve: resolveJob, promise };
  pendingCardPreviews.set(url, job);
  cardPreviewQueue.push(job);
  drainCardPreviewQueue();
  return promise;
}

export function preloadCardPreviewGroup(urls: string[]) {
  for (const url of new Set(urls.filter(Boolean))) {
    void preloadCardPreview(url, "background");
  }
}

export function pauseCardPreviewBackground() {
  backgroundPauseDepth += 1;
  let finished = false;
  return () => {
    if (finished) return;
    finished = true;
    backgroundPauseDepth = Math.max(0, backgroundPauseDepth - 1);
    drainCardPreviewQueue();
  };
}
