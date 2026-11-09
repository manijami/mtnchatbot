/**
 * MTN fork: the MTN layout (top bar, MTN sidebar, Office cards) is opt-in per deployment through
 * `interface.mtnLayout` in librechat.yaml. Off (the default) means the upstream layout, unchanged.
 */
import { useEffect, useState } from 'react';
import { useGetStartupConfig } from '~/data-provider';

export function useMtnLayout(): boolean {
  const { data: startupConfig } = useGetStartupConfig();
  return startupConfig?.interface?.mtnLayout === true;
}

/** Design-asset slots published by the branding image (`/assets/mtn/assets.json`). */
type AssetManifest = { official: string[] };

let manifestPromise: Promise<AssetManifest> | null = null;

function loadManifest(): Promise<AssetManifest> {
  if (manifestPromise == null) {
    manifestPromise = fetch('/assets/mtn/assets.json', {
      credentials: 'same-origin',
      /** Revalidate: the list changes whenever the branding image is rebuilt with new assets. */
      cache: 'no-cache',
    })
      .then((response) => (response.ok ? response.json() : { official: [] }))
      .then((data: Partial<AssetManifest>) => ({
        official: Array.isArray(data?.official) ? data.official : [],
      }))
      .catch(() => ({ official: [] }));
  }
  return manifestPromise;
}

/** Test seam: forget the cached manifest. */
export function resetMtnAssetManifest(): void {
  manifestPromise = null;
}

/** Whether an official asset fills `slot` (for example `logo/logo`). False until known. */
export function useMtnOfficialAsset(slot: string): boolean {
  const [official, setOfficial] = useState(false);
  useEffect(() => {
    let active = true;
    loadManifest().then((manifest) => {
      if (active) {
        setOfficial(manifest.official.includes(slot));
      }
    });
    return () => {
      active = false;
    };
  }, [slot]);
  return official;
}

/** Initials for an avatar: first letters of the first and last name parts. */
export function initialsOf(name?: string | null): string {
  const parts = (name ?? '').trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) {
    return '';
  }
  const first = parts[0][0] ?? '';
  const last = parts.length > 1 ? (parts[parts.length - 1][0] ?? '') : '';
  return (first + last).toUpperCase();
}
