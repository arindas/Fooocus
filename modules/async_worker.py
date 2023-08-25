import threading


buffer = []
outputs = []


def worker():
    global buffer, outputs

    import time
    import shared
    import random
    import modules.default_pipeline as pipeline
    import modules.path
    import modules.patch

    from modules.sdxl_styles import apply_style, aspect_ratios
    from modules.private_logger import log
    
    IS_WANDB_INSTALLED = False
    try:
        import wandb
        from modules.private_logger import log_to_wandb
        IS_WANDB_INSTALLED = True
    except:
        IS_WANDB_INSTALLED = False

    try:
        async_gradio_app = shared.gradio_root
        flag = f'''App started successful. Use the app with {str(async_gradio_app.local_url)} or {str(async_gradio_app.server_name)}:{str(async_gradio_app.server_port)}'''
        if async_gradio_app.share:
            flag += f''' or {async_gradio_app.share_url}'''
        print(flag)
    except Exception as e:
        print(e)

    def handler(task):
        prompt, negative_prompt, style_selction, performance_selction, \
        aspect_ratios_selction, image_number, image_seed, sharpness, base_model_name, refiner_model_name, \
        l1, w1, l2, w2, l3, w3, l4, w4, l5, w5 = task

        loras = [(l1, w1), (l2, w2), (l3, w3), (l4, w4), (l5, w5)]

        modules.patch.sharpness = sharpness

        pipeline.refresh_base_model(base_model_name)
        pipeline.refresh_refiner_model(refiner_model_name)
        pipeline.refresh_loras(loras)
        pipeline.clean_prompt_cond_caches()

        p_txt, n_txt = apply_style(style_selction, prompt, negative_prompt)

        if performance_selction == 'Speed':
            steps = 30
            switch = 20
        else:
            steps = 60
            switch = 40

        width, height = aspect_ratios[aspect_ratios_selction]

        results = []
        seed = image_seed
        max_seed = int(1024*1024*1024)

        if not isinstance(seed, int):
            seed = random.randint(1, max_seed)
        if seed < 0:
            seed = - seed
        seed = seed % max_seed

        all_steps = steps * image_number
        
        if IS_WANDB_INSTALLED:
            config_dict = {
                "Prompt": prompt,
                "Negative Prompt": negative_prompt,
                "Style": style_selction,
                "Performance": performance_selction,
                "Resolution": {"width": width, "height": height},
                "Number of Images": image_number,
                "Number of Steps": steps,
                "Image Seed": image_seed,
                "Seed": seed,
                "Sharpness": sharpness,
                "Base Model": base_model_name,
                "Refiner Model": refiner_model_name,
                "LoRA Weights": {},
            }
            for n, w in loras:
                if n != 'None':
                    config_dict["LoRA Weights"][f"LoRA [{n}] Weight"] = w
            wandb.init(job_type="text-to-image", config=config_dict)

        def callback(step, x0, x, total_steps, y):
            done_steps = i * steps + step
            outputs.append(['preview', (
                int(100.0 * float(done_steps) / float(all_steps)),
                f'Step {step}/{total_steps} in the {i}-th Sampling',
                y)])
        
        wandb_table = None
        if IS_WANDB_INSTALLED:
            wandb_table = wandb.Table(columns=["Prompt", "Negative Prompt", "Image"])

        for i in range(image_number):
            imgs = pipeline.process(p_txt, n_txt, steps, switch, width, height, seed, callback=callback)

            for x in imgs:
                d = [
                    ('Prompt', prompt),
                    ('Negative Prompt', negative_prompt),
                    ('Style', style_selction),
                    ('Performance', performance_selction),
                    ('Resolution', str((width, height))),
                    ('Sharpness', sharpness),
                    ('Base Model', base_model_name),
                    ('Refiner Model', refiner_model_name),
                    ('Seed', seed)
                ]
                for n, w in loras:
                    if n != 'None':
                        d.append((f'LoRA [{n}] weight', w))
                log(x, d)
                
                if IS_WANDB_INSTALLED:
                    wandb_table = log_to_wandb(x, d, wandb_table)

            seed += 1
            results += imgs

        outputs.append(['results', results])
        
        if IS_WANDB_INSTALLED:
            wandb.log({"Generation-Table": wandb_table})
            wandb.finish()

        return

    while True:
        time.sleep(0.01)
        if len(buffer) > 0:
            task = buffer.pop(0)
            handler(task)
    pass


threading.Thread(target=worker, daemon=True).start()
