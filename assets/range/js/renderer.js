// Standalone Three.js Renderer with ACESFilmic Tone Mapping and Soft Shadows

export function initRenderer() {
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x87CEEB); // Sky blue
    scene.fog = new THREE.FogExp2(0x87CEEB, 0.0015);
    
    const camera = new THREE.PerspectiveCamera(55, window.innerWidth / window.innerHeight, 0.1, 1500);
    camera.position.set(0, 1.75, 4.6); // Elevated and pulled back from tee mat
    
    const canvasElement = document.getElementById('three-canvas') || undefined;
    const renderer = new THREE.WebGLRenderer({
        canvas: canvasElement,
        antialias: true,
        alpha: false,
        powerPreference: "high-performance"
    });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    
    // ACESFilmic tone mapping for rich cinematic color depth
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.30;
    
    // Enable soft PCF shadows
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    // sRGB output (r150+ replaces .outputEncoding with .outputColorSpace)
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    
    if (!canvasElement) {
        document.body.appendChild(renderer.domElement);
    }
    
    // Ambient natural daylight fill
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.1);
    scene.add(ambientLight);

    // Hemisphere natural sky & grass bounce lighting
    const hemiLight = new THREE.HemisphereLight(0xffffff, 0x5a7d36, 1.3);
    scene.add(hemiLight);
    
    // Directional Sun Light casting realistic shadows
    const sunLight = new THREE.DirectionalLight(0xfffaee, 2.4);
    sunLight.position.set(70, 140, 50);
    sunLight.castShadow = true;
    sunLight.shadow.mapSize.width = 2048;
    sunLight.shadow.mapSize.height = 2048;
    sunLight.shadow.camera.near = 0.5;
    sunLight.shadow.camera.far = 600;
    
    const d = 150;
    sunLight.shadow.camera.left = -d;
    sunLight.shadow.camera.right = d;
    sunLight.shadow.camera.top = d;
    sunLight.shadow.camera.bottom = -d;
    sunLight.shadow.bias = -0.0005;
    
    scene.add(sunLight);
    
    // Handle window resize
    window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    });
    
    return { scene, camera, renderer, sunLight };
}
