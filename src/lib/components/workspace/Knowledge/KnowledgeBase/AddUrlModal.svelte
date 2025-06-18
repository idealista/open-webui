<script lang="ts">
	import { toast } from 'svelte-sonner';

	import { onMount, getContext, createEventDispatcher } from 'svelte';
	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	import Modal from '$lib/components/common/Modal.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	
	export let show = false;

	let url = '';
	let mode: 'scrape' | 'crawl' = 'scrape';

    // Basic URL validation
    function isValidUrl(url: string) {
        const pattern = /^(https?:\/\/)?([a-zA-Z0-9-]+\.)+[a-zA-Z0-9]{2,}(\/[^\s]*)?$/;
        return pattern.test(url);
    }

</script>

<Modal size="sm" containerClassName="" className="w-full max-w-md bg-white dark:bg-gray-900" bind:show>
	<div class="absolute top-0 right-0 p-3">
		<button
			class="self-center dark:text-white"
			type="button"
			on:click={() => {
				show = false;
			}}
		>
			<XMark className="size-3.5" />
		</button>
	</div>

	<div class="flex flex-col w-full p-6 dark:text-gray-200">
		<form
			class="flex flex-col w-full"
			on:submit|preventDefault={() => {
				if (!url.trim()) {
					toast.error($i18n.t('Please enter a URL.'));
					return;
				}

				if (!isValidUrl(url.trim())) {
					toast.error($i18n.t('Please enter a valid URL.'));
					return;
				}

				dispatch('submit', { url: url.trim(), mode });
				show = false;
				url = '';
				mode = 'scrape';
			}}
		>
			<div class="w-full flex flex-col gap-4">
				<h2 class="text-xl font-semibold">{$i18n.t('Add URL')}</h2>
				
				<div class="w-full">
					<label for="url-input" class="block text-sm font-medium mb-2">
						{$i18n.t('URL')}
					</label>
					<input
						id="url-input"
						class="w-full p-3 border rounded-lg dark:border-gray-700 bg-transparent focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
						type="text"
						bind:value={url}
						placeholder={$i18n.t('Enter URL')}
						required
					/>
				</div>

				<div class="w-full">
					<label for="mode-select" class="block text-sm font-medium mb-2">
						{$i18n.t('Mode')}
					</label>
					<select
						id="mode-select"
						bind:value={mode}
						class="w-full p-3 border rounded-lg dark:border-gray-700 bg-transparent dark:bg-gray-800 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
					>
						<option value="scrape" class="dark:bg-gray-800 dark:text-white">{$i18n.t('Scrape')} - {$i18n.t('Single page only')}</option>
						<option value="crawl" class="dark:bg-gray-800 dark:text-white">{$i18n.t('Crawl')} - {$i18n.t('Full website crawl')}</option>
					</select>
					<p class="text-xs text-gray-500 mt-1">
						{mode === 'scrape' 
							? $i18n.t('Extract content from the specified page only')
							: $i18n.t('Crawl the entire website starting from this URL')
						}
					</p>
				</div>
			</div>

			<div class="flex flex-row items-center justify-end text-sm font-medium mt-6 gap-2">
				<button
					type="button"
					class="px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition"
					on:click={() => {
						show = false;
					}}
				>
					{$i18n.t('Cancel')}
				</button>
				<Tooltip content={$i18n.t('Add')}>
					<button
						class="px-4 py-2 bg-black text-white dark:bg-white dark:text-black transition rounded-lg hover:bg-gray-800 dark:hover:bg-gray-200"
						type="submit"
					>
						{$i18n.t('Add')}
					</button>
				</Tooltip>
			</div>
		</form>
	</div>
</Modal>

<style>
	input::-webkit-outer-spin-button,
	input::-webkit-inner-spin-button {
		/* display: none; <- Crashes Chrome on hover */
		-webkit-appearance: none;
		margin: 0; /* <-- Apparently some margin are still there even though it's hidden */
	}

	.tabs::-webkit-scrollbar {
		display: none; /* for Chrome, Safari and Opera */
	}

	.tabs {
		-ms-overflow-style: none; /* IE and Edge */
		scrollbar-width: none; /* Firefox */
	}

	input[type='number'] {
		-moz-appearance: textfield; /* Firefox */
	}
</style>
