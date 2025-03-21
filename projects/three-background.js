// Three.js background fix
function initThreeBackground() {
    // Create a container for the Three.js canvas if it doesn't exist
    let container = document.getElementById('three-background');
    if (!container) {
        container = document.createElement('div');
        container.id = 'three-background';
        container.style.position = 'fixed';
        container.style.top = '0';
        container.style.left = '0';
        container.style.width = '100%';
        container.style.height = '100%';
        container.style.zIndex = '-1';
        container.style.opacity = '1';
        document.body.prepend(container);
    } else {
        // Clear existing content
        container.innerHTML = '';
    }

    // Initialize Three.js scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0f1418); // Matching your dark background
    
    // Create camera
    const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.z = 30;
    
    // Create renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    container.appendChild(renderer.domElement);
    
    // Create stars
    const starGeometry = new THREE.BufferGeometry();
    const starCount = 500;
    
    const positions = new Float32Array(starCount * 3);
    const sizes = new Float32Array(starCount);
    
    for (let i = 0; i < starCount; i++) {
        const i3 = i * 3;
        positions[i3] = (Math.random() - 0.5) * 100;
        positions[i3 + 1] = (Math.random() - 0.5) * 100;
        positions[i3 + 2] = (Math.random() - 0.5) * 100;
        
        sizes[i] = Math.random() * 2;
    }
    
    starGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    starGeometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1));
    
    // Star shader material
    const starMaterial = new THREE.ShaderMaterial({
        uniforms: {
            color: { value: new THREE.Color(0x4C9CFF) },
            time: { value: 0 }
        },
        vertexShader: `
            attribute float size;
            varying float vSize;
            uniform float time;
            
            void main() {
                vSize = size;
                vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
                gl_PointSize = size * (300.0 / -mvPosition.z);
                gl_Position = projectionMatrix * mvPosition;
            }
        `,
        fragmentShader: `
            uniform vec3 color;
            varying float vSize;
            
            void main() {
                if (length(gl_PointCoord - vec2(0.5, 0.5)) > 0.5) discard;
                gl_FragColor = vec4(color, 1.0);
            }
        `,
        transparent: true,
        blending: THREE.AdditiveBlending
    });
    
    const stars = new THREE.Points(starGeometry, starMaterial);
    scene.add(stars);
    
    // Add a subtle glow in the center
    const glowGeometry = new THREE.SphereGeometry(5, 32, 32);
    const glowMaterial = new THREE.ShaderMaterial({
        uniforms: {
            color1: { value: new THREE.Color(0x4C9CFF) },
            color2: { value: new THREE.Color(0x4CEBB7) }
        },
        vertexShader: `
            varying vec3 vNormal;
            
            void main() {
                vNormal = normalize(normalMatrix * normal);
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
        `,
        fragmentShader: `
            uniform vec3 color1;
            uniform vec3 color2;
            varying vec3 vNormal;
            
            void main() {
                float intensity = pow(0.7 - dot(vNormal, vec3(0.0, 0.0, 1.0)), 4.0);
                vec3 glow = mix(color1, color2, 0.5 + 0.5 * sin(vNormal.x * 10.0));
                gl_FragColor = vec4(glow, 1.0) * intensity;
            }
        `,
        side: THREE.BackSide,
        blending: THREE.AdditiveBlending,
        transparent: true
    });
    
    const glowMesh = new THREE.Mesh(glowGeometry, glowMaterial);
    glowMesh.position.set(0, 0, -15);
    scene.add(glowMesh);
    
    // Handle window resize
    window.addEventListener('resize', () => {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    });
    
    // Mouse movement effect
    let mouseX = 0;
    let mouseY = 0;
    
    document.addEventListener('mousemove', (event) => {
        mouseX = (event.clientX / window.innerWidth) * 2 - 1;
        mouseY = -(event.clientY / window.innerHeight) * 2 + 1;
    });
    
    // Animation loop
    let time = 0;
    function animate() {
        requestAnimationFrame(animate);
        
        time += 0.005;
        starMaterial.uniforms.time.value = time;
        
        // Rotate stars based on mouse
        stars.rotation.x += 0.0005;
        stars.rotation.y += 0.0005;
        stars.rotation.x += mouseY * 0.0002;
        stars.rotation.y += mouseX * 0.0002;
        
        // Rotate glow
        glowMesh.rotation.x = time * 0.2;
        glowMesh.rotation.y = time * 0.4;
        
        renderer.render(scene, camera);
    }
    
    animate();
}

// Call this function after Three.js is loaded
async function loadAndInitThree() {
    if (typeof THREE === 'undefined') {
        try {
            // Create script element for Three.js
            const threeScript = document.createElement('script');
            threeScript.src = 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js';
            threeScript.async = true;
            
            // Create a promise to wait for the script to load
            const threeLoaded = new Promise((resolve, reject) => {
                threeScript.onload = resolve;
                threeScript.onerror = reject;
            });
            
            // Add the script to the document
            document.head.appendChild(threeScript);
            
            // Wait for the script to load
            await threeLoaded;
            
            // Initialize the Three.js background
            initThreeBackground();
        } catch (error) {
            console.error('Failed to load Three.js:', error);
        }
    } else {
        // Three.js already loaded, initialize background
        initThreeBackground();
    }
}

// Call when DOM is loaded
document.addEventListener('DOMContentLoaded', loadAndInitThree);