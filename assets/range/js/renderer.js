// Standalone Three.js Renderer with ACESFilmic Tone Mapping and Soft Shadows

export function initRenderer() {
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x87CEEB); // Sky blue
    scene.fog = new THREE.FogExp2(0x87CEEB, 0.0015);
    
    const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.1, 1500);
    camera.position.set(0, 1.75, 4.6); // Elevated and pulled back from tee mat
    
    const canvasElement = document.getElementById('three-canvas') || undefined;
    let renderer;
    try {
        renderer = new THREE.WebGLRenderer({
            canvas: canvasElement,
            antialias: true,
            alpha: false,
            powerPreference: "high-performance"
        });
    } catch (error) {
        console.warn('[Range] WebGL unavailable; retaining telemetry and mode controls.', error);
        return { scene, camera, renderer: null, sunLight: null };
    }
    const viewport = document.getElementById('range-scene') || document.body;
    function resizeRenderer() {
        const width = viewport.clientWidth || 960;
        const height = viewport.clientHeight || 540;
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height, false);
    }
    resizeRenderer();
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    
    // ACESFilmic tone mapping for rich cinematic color depth
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    
    // Enable soft PCF shadows
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    // sRGB output (r150+ replaces .outputEncoding with .outputColorSpace)
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    
    if (!canvasElement) {
        document.body.appendChild(renderer.domElement);
    }
    
    // Ambient natural daylight fill
    const ambientLight = new THREE.AmbientLight(0xe9f0f5, 0.38);
    scene.add(ambientLight);

    // Hemisphere natural sky & grass bounce lighting
    const hemiLight = new THREE.HemisphereLight(0xc8e0f0, 0x64734c, 0.72);
    scene.add(hemiLight);
    
    // Directional Sun Light casting realistic shadows
    const sunLight = new THREE.DirectionalLight(0xffedce, 2.0);
    sunLight.position.set(-80, 110, 40);
    sunLight.castShadow = true;
    sunLight.shadow.mapSize.width = 2048;
    sunLight.shadow.mapSize.height = 2048;
    sunLight.shadow.camera.near = 0.5;
    sunLight.shadow.camera.far = 600;
    
    const d = 90;
    sunLight.shadow.camera.left = -d;
    sunLight.shadow.camera.right = d;
    sunLight.shadow.camera.top = d;
    sunLight.shadow.camera.bottom = -d;
    sunLight.shadow.bias = -0.00015;
    sunLight.shadow.normalBias = 0.08;
    sunLight.shadow.radius = 2;
    
    scene.add(sunLight);
    
    // The canvas is inset in the studio workspace, not the whole window.
    window.addEventListener('resize', resizeRenderer);
    if (typeof ResizeObserver !== 'undefined') {
        const observer = new ResizeObserver(resizeRenderer);
        observer.observe(viewport);
    }

    return { scene, camera, renderer, sunLight };
}
