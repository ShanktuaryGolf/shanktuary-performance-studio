// Standalone Three.js Renderer with ACESFilmic Tone Mapping and Soft Shadows

export function initRenderer() {
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x87CEEB); // Sky blue
    scene.fog = new THREE.FogExp2(0x87CEEB, 0.0015);
    
    const camera = new THREE.PerspectiveCamera(65, window.innerWidth / window.innerHeight, 0.1, 1200);
    camera.position.set(0, 2.2, 6); // Behind the tee looking down -Z
    
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "high-performance" });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    
    // ACESFilmic tone mapping for rich cinematic color depth
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    
    // Enable soft PCF shadows
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    
    document.body.appendChild(renderer.domElement);
    
    // Ambient natural fill light
    const ambientLight = new THREE.AmbientLight(0xddeeff, 0.6);
    scene.add(ambientLight);
    
    // Directional Sun Light casting realistic shadows
    const sunLight = new THREE.DirectionalLight(0xfffaed, 1.8);
    sunLight.position.set(60, 120, 40);
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
